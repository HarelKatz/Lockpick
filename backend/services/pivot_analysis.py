"""Pivot path analysis — path finding over the aggregated edge graph using NetworkX."""
from typing import Optional

import networkx as nx
from sqlalchemy.orm import Session

from schemas import (
    GraphEdge,
    GraphResponse,
    PathFinderRequest,
    PathFinderResponse,
    PathResult,
)
from services.graph_builder import build_graph

_MAX_DEPTH = 8
_MAX_PATHS = 30


def find_paths(
    db: Session,
    op_id: str,
    request: PathFinderRequest,
    graph: Optional[GraphResponse] = None,
) -> PathFinderResponse:
    """Find pivot paths between two hosts, with optional waypoint constraints.

    Pass a pre-built *graph* to avoid an extra ``build_graph`` call when the
    caller already holds one (e.g. ``generate_path_commands``).
    """
    if graph is None:
        graph = build_graph(db, op_id)

    # Build directed graph and edge lookup
    G: nx.DiGraph = nx.DiGraph()
    edge_lookup: dict[tuple[str, str], GraphEdge] = {}
    for edge in graph.edges:
        G.add_edge(edge.src_host_id, edge.dst_host_id)
        edge_lookup[(edge.src_host_id, edge.dst_host_id)] = edge

    src = request.src_host_id
    dst = request.dst_host_id

    if src == dst:
        return PathFinderResponse(paths=[], truncated=False)

    # Find raw paths — collect one extra to detect truncation without a false positive
    if request.mode == "shortest":
        raw_paths = _nx_shortest(G, src, dst)
    else:
        raw_paths = _nx_all(G, src, dst, cap=_MAX_PATHS + 1)

    # Filter by waypoint constraints
    filtered = _apply_waypoints(raw_paths, request.waypoints)

    truncated = len(filtered) > _MAX_PATHS

    # Build PathResult objects
    results: list[PathResult] = []
    for path in filtered[:_MAX_PATHS]:
        path_edges = [
            edge_lookup[(path[i], path[i + 1])]
            for i in range(len(path) - 1)
            if (path[i], path[i + 1]) in edge_lookup
        ]
        results.append(PathResult(host_ids=path, edges=path_edges))

    return PathFinderResponse(paths=results, truncated=truncated)


def _nx_shortest(G: nx.DiGraph, src: str, dst: str) -> list[list[str]]:
    """Return the shortest path from src to dst, or empty list if none exists."""
    try:
        path = nx.shortest_path(G, src, dst)
        if len(path) - 1 > _MAX_DEPTH:
            return []
        return [path]
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def _nx_all(G: nx.DiGraph, src: str, dst: str, cap: int = _MAX_PATHS) -> list[list[str]]:
    """Return all simple paths up to _MAX_DEPTH hops, capped at *cap* entries.

    Pass ``cap=_MAX_PATHS + 1`` to collect one extra path so the caller can
    detect truncation without a false positive when exactly _MAX_PATHS paths exist.
    """
    results: list[list[str]] = []
    try:
        for path in nx.all_simple_paths(G, src, dst, cutoff=_MAX_DEPTH):
            results.append(path)
            if len(results) >= cap:
                break
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass
    return results


def _apply_waypoints(
    paths: list[list[str]],
    waypoints: list,
) -> list[list[str]]:
    """Filter paths to only those satisfying all waypoint constraints."""
    if not waypoints:
        return paths

    result: list[list[str]] = []
    for path in paths:
        valid = True
        for wp in waypoints:
            host_id = wp.host_id
            position = wp.position
            relative_to = wp.relative_to

            if position == "anywhere":
                # Must appear somewhere between src and dst (not at endpoints)
                if host_id not in path[1:-1]:
                    valid = False
                    break

            elif position == "after":
                if not relative_to:
                    # "after src" by default — must be the first hop after src
                    if len(path) < 2 or path[1] != host_id:
                        valid = False
                        break
                else:
                    # Must appear immediately after relative_to
                    try:
                        idx = path.index(relative_to)
                        if idx + 1 >= len(path) or path[idx + 1] != host_id:
                            valid = False
                            break
                    except ValueError:
                        valid = False
                        break

            elif position == "before":
                if not relative_to:
                    # "before dst" by default — must be the last hop before dst
                    if len(path) < 2 or path[-2] != host_id:
                        valid = False
                        break
                else:
                    # Must appear immediately before relative_to
                    try:
                        idx = path.index(relative_to)
                        if idx - 1 < 0 or path[idx - 1] != host_id:
                            valid = False
                            break
                    except ValueError:
                        valid = False
                        break

        if valid:
            result.append(path)
    return result
