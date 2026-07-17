"""Soundness & optimality properties for the pivot path finder (services.pivot_analysis.find_paths).

Style B, mirroring test_graph_invariants.py: build a generated op through the REST OpBuilder,
build the graph, then call find_paths directly against the shared session. Every path the finder
returns, for ANY generated topology, must satisfy these properties.

=== ANTI-TAUTOLOGY (mirrors the _RANK convention in test_graph_invariants.py:23-26) ===
The expected shortest-path length comes from an INDEPENDENT BFS this module writes over
graph.edges (_bfs_dist). We must NEVER call nx.shortest_path to compute the expected value —
that is exactly the routine find_paths uses (pivot_analysis.py:74), so reusing it would make the
optimality check circular and blind to a broken pathfinder.

=== COUPLING TO UNWEIGHTED PATHFINDING — READ BEFORE EDITING ===
test_shortest_mode_is_bfs_optimal asserts ``hop_count == BFS distance``. This holds ONLY while
find_paths is UNWEIGHTED hop-count (pivot_analysis.py builds a bare nx.DiGraph with no edge
weights). The next analytics task — "Confidence semantics + pathfinding weighting" (TODO.md:20)
— will weight find_paths so it prefers executable hops, at which point "fewest hops == shortest"
no longer holds and this property must be rewritten to compare against a weighted shortest
distance. This regression net existing before that refactor is exactly why the item is sequenced
"Do first".
"""
from __future__ import annotations

from collections import deque

import pytest
from hypothesis import given

from schemas import PathFinderRequest
from services.graph_builder import build_graph
from services.pivot_analysis import _MAX_DEPTH, _MAX_PATHS, find_paths
from tests.opbuilder import OpBuilder
from tests.test_invariants.strategies import structure_topologies

pytestmark = pytest.mark.property


# ─── Independent reference implementations (deliberately NOT networkx) ────────────

def _adjacency(edges) -> dict[str, set[str]]:
    """Directed adjacency over graph.edges — the SAME topology find_paths feeds its nx.DiGraph
    (pivot_analysis.py:38), rebuilt independently. Isolated hosts (no edges) never appear, so
    BFS treats them as unreachable — matching the impl's swallowed NodeNotFound (pivot_analysis
    .py:78,94)."""
    adj: dict[str, set[str]] = {}
    for e in edges:
        adj.setdefault(e.src_host_id, set()).add(e.dst_host_id)
    return adj


def _bfs_dist(adj: dict[str, set[str]], src: str, dst: str) -> int | None:
    """Fewest-hops distance src→dst over the directed edge set, or None if unreachable.
    Independent of nx.shortest_path (anti-tautology)."""
    if src == dst:
        return 0
    seen = {src}
    queue = deque([(src, 0)])
    while queue:
        node, dist = queue.popleft()
        for nxt in adj.get(node, ()):
            if nxt == dst:
                return dist + 1
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, dist + 1))
    return None


def _enumerate_simple_paths(adj, src, dst, *, cutoff: int, cap: int) -> list[tuple[str, ...]]:
    """From-scratch enumeration of simple paths src→dst using <= ``cutoff`` EDGES, matching
    nx.all_simple_paths(cutoff=_MAX_DEPTH) — cutoff is measured in edges, confirmed by the
    8-in/9-out unit tests (test_pivot_analysis.py:157-183). Neighbours walked in sorted order
    for determinism; stops once ``cap`` paths are found so a dense outlier can't blow up."""
    results: list[tuple[str, ...]] = []

    def dfs(node, path, seen):
        if len(results) >= cap:
            return
        if node == dst:
            results.append(tuple(path))
            return
        if len(path) - 1 >= cutoff:  # already at ``cutoff`` edges — one more would exceed it
            return
        for nxt in sorted(adj.get(node, ())):
            if nxt not in seen:
                seen.add(nxt)
                path.append(nxt)
                dfs(nxt, path, seen)
                path.pop()
                seen.discard(nxt)

    if src != dst:
        dfs(src, [src], {src})
    return results


def _sample_pairs(host_ids: dict[str, str], edges) -> list[tuple[str, str]]:
    """<=50 deterministic ordered (src, dst) pairs per topology.

    Hosts are taken in index order (``list(host_ids.values())`` preserves the generator's
    order). Forward pairs (lower→higher index) are reachability CANDIDATES; reverse pairs are
    unreachable because the generated graph is a DAG in host-index order (generate_random_
    network.py:165-188) — so both the reachable and the unreachable branches get exercised. The
    DAG ordering is only a COVERAGE heuristic; correctness never relies on it (BFS decides per
    pair). The first few real edges are added to guarantee some directly-connected (d==1) pairs.
    """
    ordered = list(host_ids.values())
    n = len(ordered)
    idx = sorted({round(k * (n - 1) / 6) for k in range(7)})  # <=7 spread indices
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []

    def add(a: str, b: str) -> None:
        if a != b and (a, b) not in seen:
            seen.add((a, b))
            pairs.append((a, b))

    for i in idx:            # <= 7*6 = 42 within-set ordered pairs
        for j in idx:
            add(ordered[i], ordered[j])
    for e in edges[:8]:      # guarantee some directly-connected (d==1) coverage
        add(e.src_host_id, e.dst_host_id)
    return pairs


# ─── Property 1: every returned path is a real, simple walk with correct endpoints ──

@given(topo=structure_topologies())
def test_every_returned_path_is_a_real_walk(client, db_session, topo):
    lo = OpBuilder(client).apply_topology(topo)
    graph = build_graph(db_session, lo.op_id)
    adj = _adjacency(graph.edges)

    # src == dst → [] before any nx call (pivot_analysis.py:44). Pinned once.
    any_id = next(iter(lo.host_ids.values()))
    same = PathFinderRequest(src_host_id=any_id, dst_host_id=any_id, mode="all")
    assert find_paths(db_session, lo.op_id, same, graph=graph).paths == []

    for src, dst in _sample_pairs(lo.host_ids, graph.edges):
        for mode in ("shortest", "all"):
            req = PathFinderRequest(src_host_id=src, dst_host_id=dst, mode=mode)
            resp = find_paths(db_session, lo.op_id, req, graph=graph)

            assert isinstance(resp.truncated, bool)
            assert len(resp.paths) <= _MAX_PATHS
            if mode == "shortest":
                assert len(resp.paths) <= 1
                assert resp.truncated is False

            for p in resp.paths:
                assert p.host_ids[0] == src                          # correct src endpoint
                assert p.host_ids[-1] == dst                         # correct dst endpoint
                assert len(set(p.host_ids)) == len(p.host_ids)       # simple: no repeated nodes
                assert len(p.host_ids) - 1 <= _MAX_DEPTH             # depth bound
                for a, b in zip(p.host_ids, p.host_ids[1:]):         # every hop is a real edge
                    assert b in adj.get(a, set())
                # p.edges aligned: exactly one edge per hop, endpoints matching the host_ids
                assert len(p.edges) == len(p.host_ids) - 1
                for edge, a, b in zip(p.edges, p.host_ids, p.host_ids[1:]):
                    assert edge.src_host_id == a
                    assert edge.dst_host_id == b


# ─── Property 2: shortest mode returns the true BFS-optimal path (flagship) ──────────

@given(topo=structure_topologies())
def test_shortest_mode_is_bfs_optimal(client, db_session, topo):
    # See the module header: fewest-hops == BFS distance holds ONLY while find_paths is
    # unweighted. The weighting task (TODO.md:20) must rewrite this comparison.
    lo = OpBuilder(client).apply_topology(topo)
    graph = build_graph(db_session, lo.op_id)
    adj = _adjacency(graph.edges)

    for src, dst in _sample_pairs(lo.host_ids, graph.edges):
        d = _bfs_dist(adj, src, dst)  # independent BFS — never nx.shortest_path
        req = PathFinderRequest(src_host_id=src, dst_host_id=dst, mode="shortest")
        resp = find_paths(db_session, lo.op_id, req, graph=graph)
        assert resp.truncated is False

        if d is None or d > _MAX_DEPTH:
            # unreachable, or the shortest path exceeds the depth cap (pivot_analysis.py:75-76)
            assert resp.paths == []
        else:
            assert len(resp.paths) == 1
            assert len(resp.paths[0].host_ids) - 1 == d  # exactly the BFS optimum


# ─── Property 3: all mode == independent simple-path enumeration (completeness) ──────

@given(topo=structure_topologies())
def test_all_mode_matches_independent_enumeration(client, db_session, topo):
    lo = OpBuilder(client).apply_topology(topo)
    graph = build_graph(db_session, lo.op_id)
    adj = _adjacency(graph.edges)

    for src, dst in _sample_pairs(lo.host_ids, graph.edges):
        req = PathFinderRequest(src_host_id=src, dst_host_id=dst, mode="all")
        resp = find_paths(db_session, lo.op_id, req, graph=graph)
        expected = _enumerate_simple_paths(adj, src, dst, cutoff=_MAX_DEPTH, cap=_MAX_PATHS + 1)

        # (a) existence equivalence — guards the all-mode branch
        assert bool(resp.paths) == (len(expected) > 0)
        # (b) returned paths are distinct
        got = [tuple(p.host_ids) for p in resp.paths]
        assert len(set(got)) == len(got)
        # (c) full-set equality when NEITHER side is truncated (the strong catch). When either
        # side is capped the returned/enumerated ORDER may differ, so only assert truncation.
        if not resp.truncated and len(expected) <= _MAX_PATHS:
            assert set(got) == set(expected)
        else:
            assert resp.truncated is True or len(resp.paths) == _MAX_PATHS
