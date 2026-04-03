"""Graph builder — aggregates CredentialLinks and ConnectionRecords into edge objects."""
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from models import ConnectionRecord, Credential, CredentialLink, Host
from schemas import (
    EvidenceItem,
    GraphEdge,
    GraphNode,
    GraphResponse,
    PivotableUser,
)

# Confidence ranking for comparison
_CONFIDENCE_RANK = {"confirmed": 2, "observed": 1, "indicator": 0}


def _max_confidence(confidences: list[str]) -> str:
    """Return the highest-ranked confidence string from a list."""
    return max(confidences, key=lambda c: _CONFIDENCE_RANK.get(c, 0))


def _derive_pivotable_users(evidence: list[EvidenceItem]) -> list[PivotableUser]:
    """Deduplicate pivot user tuples from evidence items."""
    seen: set[tuple] = set()
    result: list[PivotableUser] = []
    for e in evidence:
        if not e.src_user or not e.dst_user:
            continue
        if e.type == "key_match":
            method = "key"
        elif e.auth_method == "password":
            method = "password"
        else:
            method = "connection"
        key = (e.src_user, e.dst_user, method, e.credential_id)
        if key not in seen:
            seen.add(key)
            result.append(PivotableUser(
                src_user=e.src_user,
                dst_user=e.dst_user,
                method=method,
                credential_id=e.credential_id,
            ))
    return result


def build_graph(
    db: Session,
    op_id: str,
    host_ids: Optional[list[str]] = None,
) -> GraphResponse:
    """
    Build the graph for an operation.

    If host_ids is provided, only return nodes for those hosts
    and edges where both endpoints are in the set.
    """
    # ── Load hosts ──────────────────────────────────────────────────────────
    host_query = db.query(Host).filter(Host.op_id == op_id)
    all_hosts = host_query.all()

    if host_ids is not None:
        host_id_set = set(host_ids)
        hosts = [h for h in all_hosts if h.id in host_id_set]
    else:
        host_id_set = {h.id for h in all_hosts}
        hosts = all_hosts

    host_by_id = {h.id: h for h in hosts}

    # ── Build nodes ──────────────────────────────────────────────────────────
    nodes = [
        GraphNode(
            host_id=h.id,
            nickname=h.nickname,
            ips=[ip.ip_address for ip in h.ips],
            user_count=len(h.users),
            credential_count=len({link.credential_id for link in h.credential_links}),
        )
        for h in hosts
    ]

    # ── Load credential links for the op (join through Credential.op_id) ────
    all_links = (
        db.query(CredentialLink)
        .join(Credential, CredentialLink.credential_id == Credential.id)
        .filter(Credential.op_id == op_id)
        .all()
    )

    # Load credentials by ID for fingerprint lookup
    cred_ids = {link.credential_id for link in all_links}
    cred_by_id = {}
    if cred_ids:
        creds = db.query(Credential).filter(Credential.id.in_(cred_ids)).all()
        cred_by_id = {c.id: c for c in creds}

    # ── Load connection records ──────────────────────────────────────────────
    conn_records = (
        db.query(ConnectionRecord)
        .filter(
            ConnectionRecord.op_id == op_id,
            ConnectionRecord.src_host_id.isnot(None),
            ConnectionRecord.dst_host_id.isnot(None),
        )
        .all()
    )

    # Extend cred_by_id with any credentials referenced by connection records
    conn_cred_ids = {r.credential_id for r in conn_records if r.credential_id} - cred_ids
    if conn_cred_ids:
        extra_creds = db.query(Credential).filter(Credential.id.in_(conn_cred_ids)).all()
        cred_by_id.update({c.id: c for c in extra_creds})

    # ── Accumulate evidence per (src_host_id, dst_host_id) ──────────────────
    edge_evidence: dict[tuple[str, str], list[EvidenceItem]] = defaultdict(list)

    # Pass 1 — Key matches
    # Index: fingerprint → [(host_id, username, cred_id, relationship_type)]
    fp_map: dict[str, list[tuple[str, Optional[str], str, str]]] = defaultdict(list)
    for link in all_links:
        cred = cred_by_id.get(link.credential_id)
        if cred and cred.fingerprint:
            fp_map[cred.fingerprint].append(
                (link.host_id, link.username, link.credential_id, link.relationship_type)
            )

    for fp, entries in fp_map.items():
        found_on_disk = [
            (h, u, c) for h, u, c, r in entries if r == "found_on_disk"
        ]
        authorized_key = [
            (h, u, c) for h, u, c, r in entries if r == "authorized_key"
        ]
        for src_host, src_user, cred_id in found_on_disk:
            for dst_host, dst_user, _ in authorized_key:
                if src_host == dst_host:
                    continue  # no self-loops
                if src_host not in host_id_set or dst_host not in host_id_set:
                    continue
                src_nickname = host_by_id[src_host].nickname if src_host in host_by_id else src_host
                dst_nickname = host_by_id[dst_host].nickname if dst_host in host_by_id else dst_host
                cred_obj = cred_by_id.get(cred_id)
                edge_evidence[(src_host, dst_host)].append(EvidenceItem(
                    type="key_match",
                    detail=(
                        f"Key {fp[:16]}… found on {src_nickname}"
                        f"{f'({src_user})' if src_user else ''}"
                        f" authorized for {dst_nickname}"
                        f"{f'({dst_user})' if dst_user else ''}"
                    ),
                    credential_id=cred_id,
                    credential_fingerprint=cred_obj.fingerprint if cred_obj else None,
                    credential_name=cred_obj.name if cred_obj else None,
                    src_user=src_user,
                    dst_user=dst_user,
                    confidence="confirmed",
                ))

    # Pass 2 — Connection records
    for record in conn_records:
        src = record.src_host_id
        dst = record.dst_host_id
        if src not in host_id_set or dst not in host_id_set:
            continue

        source_file = record.source_file or ""

        if "bash_history" in source_file:
            ev_type = "bash_history"
            confidence = "indicator"
        elif "known_hosts" in source_file:
            ev_type = "known_hosts"
            confidence = "indicator"
        elif record.direction_context == "from_dst_logs" and record.credential_id:
            ev_type = "connection_log"
            confidence = "confirmed"
        elif record.direction_context == "from_dst_logs":
            ev_type = "connection_log"
            confidence = "observed"
        else:
            ev_type = "connection_log"
            confidence = "observed"

        conn_cred_obj = cred_by_id.get(record.credential_id) if record.credential_id else None
        edge_evidence[(src, dst)].append(EvidenceItem(
            type=ev_type,
            detail=(
                f"{record.connection_type.upper()} "
                f"{record.src_ip} → {record.dst_ip}"
            ),
            credential_id=record.credential_id,
            credential_fingerprint=conn_cred_obj.fingerprint if conn_cred_obj else None,
            credential_name=conn_cred_obj.name if conn_cred_obj else None,
            connection_type=record.connection_type,
            src_user=record.src_user,
            dst_user=record.dst_user,
            auth_method=record.auth_method,
            timestamp=record.timestamp,
            source_file=record.source_file,
            confidence=confidence,
        ))

    # ── Assemble edges ───────────────────────────────────────────────────────
    edges = []
    for (src, dst), evidence_list in edge_evidence.items():
        best_confidence = _max_confidence([e.confidence for e in evidence_list])
        edges.append(GraphEdge(
            src_host_id=src,
            dst_host_id=dst,
            confidence=best_confidence,
            evidence=evidence_list,
            pivotable_users=_derive_pivotable_users(evidence_list),
        ))

    return GraphResponse(nodes=nodes, edges=edges)


def expand_host(
    db: Session,
    op_id: str,
    host_id: str,
    evidence_type: str = "all",
) -> GraphResponse:
    """
    Return the target host plus all directly adjacent hosts and edges.
    evidence_type filters which evidence types to include:
    'all' | 'key_match' | 'connection_log' | 'indicator'
    """
    full = build_graph(db, op_id, host_ids=None)

    # Filter edges touching this host
    touching_edges = [
        e for e in full.edges
        if e.src_host_id == host_id or e.dst_host_id == host_id
    ]

    # Apply evidence_type filter
    if evidence_type != "all":
        filtered_edges = []
        for edge in touching_edges:
            if evidence_type == "key_match":
                kept = [e for e in edge.evidence if e.type == "key_match"]
            elif evidence_type == "connection_log":
                kept = [e for e in edge.evidence if e.type == "connection_log"]
            elif evidence_type == "indicator":
                kept = [e for e in edge.evidence if e.confidence == "indicator"]
            else:
                kept = edge.evidence
            if kept:
                best = _max_confidence([e.confidence for e in kept])
                filtered_edges.append(GraphEdge(
                    src_host_id=edge.src_host_id,
                    dst_host_id=edge.dst_host_id,
                    confidence=best,
                    evidence=kept,
                    pivotable_users=_derive_pivotable_users(kept),
                ))
        touching_edges = filtered_edges

    # Collect neighbor host IDs
    neighbor_ids = set()
    neighbor_ids.add(host_id)
    for edge in touching_edges:
        neighbor_ids.add(edge.src_host_id)
        neighbor_ids.add(edge.dst_host_id)

    # Filter nodes
    nodes = [n for n in full.nodes if n.host_id in neighbor_ids]

    return GraphResponse(nodes=nodes, edges=touching_edges)
