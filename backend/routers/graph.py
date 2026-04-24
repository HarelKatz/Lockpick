"""Graph endpoints — compute pivot graph on demand."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Credential, Host, HostIP
from routers.deps import get_op_or_404
from schemas import (
    GraphResponse,
    PathCommands,
    PathCommandsResponse,
    PathFinderRequest,
    PathFinderResponse,
    PathResult,
)
from services.graph_builder import build_graph, expand_host
from services.pivot_analysis import find_paths

router = APIRouter(tags=["graph"])


# ─── Command generation helpers ──────────────────────────────────────────────

def _slugify(s: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", s.lower().strip()).strip("-")
    return slug or "host"


def _best_ip(ips: list[HostIP]) -> str:
    """Return first IPv4; fall back to first entry; '<ip>' if empty."""
    for ip in ips:
        if ":" not in ip.ip_address:
            return ip.ip_address
    return ips[0].ip_address if ips else "<ip>"


def _cred_label(cred: Optional[Credential]) -> Optional[str]:
    if cred is None:
        return None
    if cred.name:
        return cred.name
    if cred.fingerprint:
        return cred.fingerprint   # already includes "SHA256:" prefix
    return None


def _build_commands(
    path: PathResult,
    hosts_by_id: dict,
    host_ips_by_host: dict,
    creds_by_id: dict,
) -> PathCommands:
    """Generate four command-format strings for a single pivot path."""
    hids = path.host_ids
    n = len(hids)

    # Build edge lookup by (src_id, dst_id) — edges can be fewer than hops if
    # some pairs are missing from the edge_lookup in pivot_analysis.
    edge_by_pair = {(e.src_host_id, e.dst_host_id): e for e in path.edges}

    # Per-hop data: hop[i] describes the step from hids[i] → hids[i+1]
    hops = []
    for i in range(n - 1):
        src_id = hids[i]
        dst_id = hids[i + 1]
        edge = edge_by_pair.get((src_id, dst_id))
        pu = edge.pivotable_users[0] if edge and edge.pivotable_users else None
        src_user = pu.src_user if pu else "<user>"
        dst_user = pu.dst_user if pu else "<user>"
        cred_id = pu.credential_id if pu else None
        cred = creds_by_id.get(cred_id) if cred_id else None
        hops.append({
            "src_id": src_id,
            "dst_id": dst_id,
            "src_nickname": (hosts_by_id[src_id].nickname if src_id in hosts_by_id else src_id[:8]),
            "dst_nickname": (hosts_by_id[dst_id].nickname if dst_id in hosts_by_id else dst_id[:8]),
            "src_ip": _best_ip(host_ips_by_host.get(src_id, [])),
            "dst_ip": _best_ip(host_ips_by_host.get(dst_id, [])),
            "src_user": src_user,
            "dst_user": dst_user,
            "cred_label": _cred_label(cred),
        })

    # ── ProxyJump one-liner ────────────────────────────────────────────────
    if n == 2:
        # Single hop — no -J needed
        h = hops[0]
        proxyjump = f"ssh {h['dst_user']}@{h['dst_ip']}"
    else:
        # Intermediate hops = hops[0] through hops[-2] (everything except last)
        jump_chain = ",".join(
            f"{h['dst_user']}@{h['dst_ip']}" for h in hops[:-1]
        )
        last = hops[-1]
        proxyjump = f"ssh -J {jump_chain} {last['dst_user']}@{last['dst_ip']}"

    # ── proxychains.conf block ─────────────────────────────────────────────
    # Intermediate hops are everything between source and final target.
    # For path [h0, h1, h2]: intermediates = [h1] only if n > 2
    # Each needs an SSH SOCKS proxy set up first.
    intermediate_hops = hops[:-1] if n > 2 else []  # exclude last hop's dst (the target)
    if not intermediate_hops:
        # Single hop — proxychains not useful; explain directly
        h = hops[0]
        proxychains = (
            "[ProxyList]\n"
            f"# Single hop — connect directly: ssh {h['dst_user']}@{h['dst_ip']}\n"
            "# No SOCKS proxy chain needed."
        )
    else:
        lines = ["[ProxyList]"]
        lines.append("# Set up one SSH SOCKS proxy per intermediate hop, then run:")
        last = hops[-1]
        lines.append(f"# proxychains ssh {last['dst_user']}@{last['dst_ip']}")
        lines.append("#")
        lines.append("# Setup commands (run from previous hop in chain):")
        port = 1080
        for h in intermediate_hops:
            lines.append(f"#   ssh -D {port} -N {h['dst_user']}@{h['dst_ip']}")
            port += 1
        lines.append("#")
        port = 1080
        for h in intermediate_hops:
            lines.append(f"socks5  127.0.0.1  {port}  # → {h['dst_nickname']}")
            port += 1
        proxychains = "\n".join(lines)

    # ── Step-by-step walkthrough ───────────────────────────────────────────
    walk_lines = []
    for i, h in enumerate(hops, start=1):
        walk_lines.append(
            f"Step {i}: From {h['src_nickname']} ({h['src_ip']}) as {h['src_user']}:"
        )
        walk_lines.append(f"  ssh {h['dst_user']}@{h['dst_ip']}")
        if h["cred_label"]:
            walk_lines.append(f"  # Credential: {h['cred_label']}")
        walk_lines.append("")
    walkthrough = "\n".join(walk_lines).rstrip()

    # ── SSH config block ───────────────────────────────────────────────────
    # Source host (hops[0].src) is where commands run from — no Host entry needed.
    # Each subsequent host in the path gets an entry.
    config_lines = []
    prev_alias: Optional[str] = None
    for i, h in enumerate(hops):
        # The destination of this hop
        alias = f"lockpick-{_slugify(h['dst_nickname'])}"
        if config_lines:
            config_lines.append("")
        config_lines.append(f"Host {alias}")
        config_lines.append(f"    Hostname {h['dst_ip']}")
        config_lines.append(f"    User {h['dst_user']}")
        if prev_alias is not None:
            config_lines.append(f"    ProxyJump {prev_alias}")
        prev_alias = alias

    if config_lines:
        config_lines.append("")
        config_lines.append(f"# Usage: ssh {prev_alias}")

    ssh_config = "\n".join(config_lines)

    return PathCommands(
        host_ids=hids,
        proxyjump=proxyjump,
        proxychains=proxychains,
        walkthrough=walkthrough,
        ssh_config=ssh_config,
    )


@router.get("/ops/{op_id}/graph", response_model=GraphResponse)
def get_graph(
    op_id: str,
    host_ids: Optional[str] = Query(default=None, description="Comma-separated host IDs"),
    db: Session = Depends(get_db),
) -> GraphResponse:
    """Return nodes and edges for an operation, optionally filtered to a host subset."""
    get_op_or_404(op_id, db)
    parsed_ids = (
        [h.strip() for h in host_ids.split(",") if h.strip()]
        if host_ids
        else None
    )
    return build_graph(db, op_id, parsed_ids)


@router.get("/ops/{op_id}/hosts/{host_id}/expand", response_model=GraphResponse)
def expand_host_endpoint(
    op_id: str,
    host_id: str,
    evidence_type: str = Query(default="all", description="all|key_match|connection_log|indicator"),
    db: Session = Depends(get_db),
) -> GraphResponse:
    """Return the target host plus all adjacent hosts and edges, filtered by evidence type."""
    get_op_or_404(op_id, db)
    return expand_host(db, op_id, host_id, evidence_type)


@router.post("/ops/{op_id}/graph/paths", response_model=PathFinderResponse)
def find_graph_paths(
    op_id: str,
    body: PathFinderRequest,
    db: Session = Depends(get_db),
) -> PathFinderResponse:
    """BFS/DFS pivot path finder. Max depth 8, max 30 paths returned."""
    get_op_or_404(op_id, db)
    return find_paths(db, op_id, body)


@router.post("/ops/{op_id}/graph/paths/commands", response_model=PathCommandsResponse)
def generate_path_commands(
    op_id: str,
    body: PathFinderRequest,
    db: Session = Depends(get_db),
) -> PathCommandsResponse:
    """Generate actionable SSH commands for every discovered pivot path. Read-only."""
    get_op_or_404(op_id, db)
    graph = build_graph(db, op_id)
    result = find_paths(db, op_id, body, graph=graph)

    if not result.paths:
        return PathCommandsResponse(paths=[], truncated=result.truncated)

    # Collect all host IDs and credential IDs referenced across all paths
    all_host_ids: set[str] = set()
    all_cred_ids: set[str] = set()
    for path in result.paths:
        all_host_ids.update(path.host_ids)
        for edge in path.edges:
            for pu in edge.pivotable_users:
                if pu.credential_id:
                    all_cred_ids.add(pu.credential_id)

    hosts = db.query(Host).filter(Host.id.in_(all_host_ids)).all()
    hosts_by_id = {h.id: h for h in hosts}

    ips = db.query(HostIP).filter(HostIP.host_id.in_(all_host_ids)).all()
    host_ips_by_host: dict[str, list[HostIP]] = {}
    for ip in ips:
        host_ips_by_host.setdefault(ip.host_id, []).append(ip)

    creds_by_id: dict[str, Credential] = {}
    if all_cred_ids:
        creds = db.query(Credential).filter(Credential.id.in_(all_cred_ids)).all()
        creds_by_id = {c.id: c for c in creds}

    commands = [
        _build_commands(path, hosts_by_id, host_ips_by_host, creds_by_id)
        for path in result.paths
    ]
    return PathCommandsResponse(paths=commands, truncated=result.truncated)
