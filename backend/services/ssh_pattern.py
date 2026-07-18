"""SSH config Host pattern matching and retroactive edge resolution."""
from __future__ import annotations

import fnmatch
import ipaddress
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import ConnectionRecord, Host, HostIP, SshConfigPattern


def _as_network(entry: str):
    """Return an ip_network for a CIDR entry, else None.

    authorized_keys `from=` accepts CIDR (`10.0.0.0/24`), which fnmatch can never
    match — it needs containment. ssh_config Host patterns never contain a `/`, so
    this branch is inert for them and both rule kinds share one matcher.
    """
    if "/" not in entry:
        return None
    try:
        return ipaddress.ip_network(entry, strict=False)
    except ValueError:
        return None


def _entry_matches(candidate: str, entry: str) -> bool:
    net = _as_network(entry)
    if net is not None:
        try:
            return ipaddress.ip_address(candidate) in net
        except ValueError:
            return False  # a hostname can't be inside a CIDR
    return fnmatch.fnmatch(candidate.lower(), entry.lower())


def ssh_match(candidate: str, aliases: list[str]) -> bool:
    """Return True if candidate matches a standing-rule entry list.

    Implements man 5 ssh_config PATTERNS semantics: * matches any string,
    ? matches one char, ! prefix negates. Case-insensitive. Additionally supports
    CIDR entries by containment, for authorized_keys `from=` ACLs.
    """
    positive = [a for a in aliases if not a.startswith("!")]
    negative = [a[1:] for a in aliases if a.startswith("!")]
    if not any(_entry_matches(candidate, p) for p in positive):
        return False
    return not any(_entry_matches(candidate, n) for n in negative)


def rule_raw_line(origin: str, pattern: str) -> str:
    """Stable identity string for a rule-derived edge — also the dedup key."""
    if origin == "authorized_keys":
        return f"authorized_keys from= ACL match: {pattern}"
    return f"ssh_config pattern match: Host {pattern}"


def build_rule_edge(
    db: Session,
    *,
    op_id: str,
    rule_host_id: str,
    matched_host_id: str,
    rule_ip: str,
    matched_ip: str,
    username: str | None,
    origin: str,
    direction: str,
    pattern: str,
    source_file: str,
) -> bool:
    """Add one rule-derived ConnectionRecord, honouring direction. True if created.

    The single place edges are materialized for BOTH standing-rule kinds and BOTH
    trigger paths (upload time and retroactive). Keeping it in one place is the point:
    the retroactive path previously hardcoded parser_file_type="ssh_config", so an
    authorized_keys rule would have been mislabelled — and therefore misclassified.
    """
    if rule_host_id == matched_host_id:
        return False  # no self-edges

    # outbound: the rule's host reaches the matched host. inbound (from= ACL): the
    # matched host is permitted to reach the rule's host — the reverse.
    if direction == "inbound":
        src_host_id, src_ip = matched_host_id, matched_ip
        dst_host_id, dst_ip = rule_host_id, rule_ip
    else:
        src_host_id, src_ip = rule_host_id, rule_ip
        dst_host_id, dst_ip = matched_host_id, matched_ip

    raw = rule_raw_line(origin, pattern)
    existing = (
        db.query(ConnectionRecord)
        .filter(
            ConnectionRecord.op_id == op_id,
            ConnectionRecord.src_host_id == src_host_id,
            ConnectionRecord.dst_host_id == dst_host_id,
            ConnectionRecord.raw_line == raw,
        )
        .first()
    )
    if existing:
        return False

    db.add(ConnectionRecord(
        id=str(uuid.uuid4()),
        op_id=op_id,
        src_host_id=src_host_id,
        src_ip=src_ip,
        src_user=username if direction == "outbound" else None,
        dst_host_id=dst_host_id,
        dst_ip=dst_ip,
        dst_user=username if direction == "inbound" else None,
        connection_type="ssh",
        direction_context="from_dst_logs" if direction == "inbound" else "from_src_logs",
        raw_line=raw,
        source_file=source_file,
        parser_file_type=origin,
        created_at=datetime.now(timezone.utc),
    ))
    return True


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

        rule_host = host_map.get(pat.source_host_id)
        if not rule_host:
            continue

        rule_ips = ips_by_host.get(pat.source_host_id, [])
        origin = pat.origin or "ssh_config"
        if build_rule_edge(
            db,
            op_id=host.op_id,
            rule_host_id=pat.source_host_id,
            matched_host_id=host.id,
            rule_ip=rule_ips[0] if rule_ips else rule_host.nickname,
            matched_ip=target_ips[0] if target_ips else host.nickname,
            username=pat.username,
            origin=origin,
            direction=pat.direction or "outbound",
            pattern=pat.pattern,
            source_file=f"{origin}_pattern",
        ):
            created += 1

    return created
