"""SSH config Host pattern matching and retroactive edge resolution."""
from __future__ import annotations

import fnmatch
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import ConnectionRecord, Host, HostIP, SshConfigPattern


def ssh_match(candidate: str, aliases: list[str]) -> bool:
    """Return True if candidate matches an SSH config Host pattern list.

    Implements man 5 ssh_config PATTERNS semantics: * matches any string,
    ? matches one char, ! prefix negates. Case-insensitive.
    """
    positive = [a for a in aliases if not a.startswith("!")]
    negative = [a[1:] for a in aliases if a.startswith("!")]
    c = candidate.lower()
    if not any(fnmatch.fnmatch(c, p.lower()) for p in positive):
        return False
    return not any(fnmatch.fnmatch(c, n.lower()) for n in negative)


def apply_patterns_to_host(db: Session, host: Host) -> int:
    """Check stored SSH config patterns for this op and flush indicator edges for matches.

    Called before db.commit() so new edges are part of the same transaction.
    Returns the number of new ConnectionRecords added.
    """
    patterns = (
        db.query(SshConfigPattern)
        .filter(SshConfigPattern.op_id == host.op_id)
        .all()
    )
    if not patterns:
        return 0

    # Bulk-fetch IPs for the target host and every pattern source host in one
    # IN(...) query, so we never rely on the caller to eager-load host.ips.
    pattern_host_ids = {p.source_host_id for p in patterns}
    all_ip_host_ids = pattern_host_ids | {host.id}
    ips_by_host: dict[str, list[str]] = defaultdict(list)
    for row in db.query(HostIP).filter(HostIP.host_id.in_(all_ip_host_ids)).all():
        ips_by_host[row.host_id].append(row.ip_address)

    target_ips = ips_by_host.get(host.id, [])
    candidates = [host.nickname] + target_ips
    created = 0

    host_map = {
        h.id: h
        for h in db.query(Host).filter(Host.id.in_(pattern_host_ids)).all()
    }

    for pat in patterns:
        if pat.source_host_id == host.id:
            continue  # no self-edges

        aliases = pat.pattern.split()
        if not any(ssh_match(c, aliases) for c in candidates):
            continue

        raw = f"ssh_config pattern match: Host {pat.pattern}"

        # Deduplicate: skip if this exact src→dst+raw_line already exists
        existing = (
            db.query(ConnectionRecord)
            .filter(
                ConnectionRecord.op_id == host.op_id,
                ConnectionRecord.src_host_id == pat.source_host_id,
                ConnectionRecord.dst_host_id == host.id,
                ConnectionRecord.raw_line == raw,
            )
            .first()
        )
        if existing:
            continue

        src_host = host_map.get(pat.source_host_id)
        if not src_host:
            continue

        src_ips = ips_by_host.get(pat.source_host_id, [])
        src_ip = src_ips[0] if src_ips else src_host.nickname
        dst_ip = target_ips[0] if target_ips else host.nickname

        db.add(ConnectionRecord(
            id=str(uuid.uuid4()),
            op_id=host.op_id,
            src_host_id=pat.source_host_id,
            src_ip=src_ip,
            src_user=pat.username,
            dst_host_id=host.id,
            dst_ip=dst_ip,
            connection_type="ssh",
            direction_context="from_src_logs",
            raw_line=raw,
            source_file="ssh_config_pattern",
            created_at=datetime.now(timezone.utc),
        ))
        created += 1

    return created
