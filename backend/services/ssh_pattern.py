"""SSH config Host pattern matching and retroactive edge resolution."""
from __future__ import annotations

import fnmatch
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import ConnectionRecord, Host, SshConfigPattern


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

    candidates = [host.nickname] + [ip.ip_address for ip in host.ips]
    created = 0

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

        src_host = db.query(Host).filter(Host.id == pat.source_host_id).first()
        if not src_host:
            continue

        src_ip = src_host.ips[0].ip_address if src_host.ips else src_host.nickname
        dst_ip = host.ips[0].ip_address if host.ips else host.nickname

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
