"""IP / hostname → Host resolver.

Best-effort: tries to match an IP or hostname string to an existing Host
record in the operation.  Returns the Host.id if found, otherwise creates a
new placeholder Host with just that IP and returns its id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import Host, HostIP


def resolve_ip(
    db: Session,
    op_id: str,
    ip_or_hostname: str,
    *,
    create_if_missing: bool = True,
) -> str | None:
    """Return a Host.id for *ip_or_hostname* within *op_id*.

    If no host currently owns that IP/hostname:
    - If *create_if_missing* is True, creates a placeholder Host and returns
      its id.
    - Otherwise returns None.
    """
    ip = ip_or_hostname.strip()
    if not ip:
        return None

    # 1. Look for an exact HostIP match inside this op.
    existing_ip = (
        db.query(HostIP)
        .join(Host, Host.id == HostIP.host_id)
        .filter(Host.op_id == op_id, HostIP.ip_address == ip)
        .first()
    )
    if existing_ip:
        return existing_ip.host_id

    # 2. Look for a Host whose nickname equals the string (handles hostnames).
    existing_host = (
        db.query(Host)
        .filter(Host.op_id == op_id, Host.nickname == ip)
        .first()
    )
    if existing_host:
        return existing_host.id

    if not create_if_missing:
        return None

    # 3. Create a placeholder host.
    host_id = str(uuid.uuid4())
    host = Host(
        id=host_id,
        op_id=op_id,
        nickname=ip,
        comment="Auto-created by parser (unresolved IP/hostname)",
        created_at=datetime.now(timezone.utc),
    )
    db.add(host)

    host_ip = HostIP(
        id=str(uuid.uuid4()),
        host_id=host_id,
        ip_address=ip,
        source="parsed",
        first_seen_at=datetime.now(timezone.utc),
    )
    db.add(host_ip)
    db.flush()

    return host_id
