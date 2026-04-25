"""IP / hostname → Host resolver.

Best-effort: tries to match an IP or hostname string to an existing Host
record in the operation.  Returns the Host.id if found, otherwise creates a
new placeholder Host with just that IP and returns its id.

Invalid or non-routable inputs (multicast, reserved, unspecified addresses,
and non-hostname strings like utmp magic values) are rejected — they never
produce a placeholder host.
"""
from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models import Host, HostIP

# RFC-1123-ish hostname validator (accepts `server1`, `web01.corp.local`).
# Rejects whitespace, underscores, slashes, colons, and other shell/path
# metacharacters that sneak in from utmp / command output parsing.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(?:\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


def _infer_addr_type(addr: str) -> str:
    """Infer the addr_type for a given IP address or hostname string."""
    if ":" in addr:
        return "ipv6"
    try:
        ipaddress.IPv4Address(addr)
        return "ipv4"
    except ValueError:
        return "hostname"


def _is_routable_address(ip_or_hostname: str) -> bool:
    """Return True if the string is a plausible routable IP or valid hostname.

    Rejects:
    - Multicast, reserved, and unspecified IP addresses (any address family).
      Loopback is filtered earlier in the pipeline (see `_is_loopback`) and
      is intentionally not rejected here — a caller that passes `127.0.0.1`
      or `::1` at this level is asking for the loopback host.
    - Hostname strings that don't conform to RFC-1123 (rejects utmp magic
      values like `consLOGIN`, `LOGIN`, `~`, and anything with whitespace).
    """
    try:
        ip_obj = ipaddress.ip_address(ip_or_hostname)
    except ValueError:
        # Not an IP — validate as a hostname.
        return bool(_HOSTNAME_RE.match(ip_or_hostname))
    return not (ip_obj.is_multicast or ip_obj.is_reserved or ip_obj.is_unspecified)


def is_unresolved_host(host: Host) -> bool:
    """Return True iff *host* has no user-authored content.

    "Unresolved" means the row exists only as a placeholder for an IP or
    hostname seen in evidence — no users, no credential links, no notes,
    no sudo rules. Two callers gate behavior on this predicate:

    * The upload pipeline's nickname-clobber path: a parser-supplied nickname
      replaces an auto-created nickname only when the host is still
      unresolved. Once an operator has attached anything (a credential link,
      a note, etc.) the nickname is treated as deliberate.
    * Phase 15 auto-merge: when a new alias collides with an unresolved host,
      the unresolved host is merged into the resolved host silently. Hosts
      that fail this predicate require an explicit operator merge instead.

    The caller MUST eager-load `host.users`, `host.credential_links`,
    `host.notes`, and `host.sudo_rules` (the first three are
    `lazy="raise_on_sql"` per Architecture Rule #19). Pass them through
    `selectinload()` on the query that produced *host*.
    """
    return (
        len(host.users) == 0
        and len(host.credential_links) == 0
        and len(host.notes) == 0
        and len(host.sudo_rules) == 0
    )


def resolve_ip(
    db: Session,
    op_id: str,
    ip_or_hostname: str,
    *,
    create_if_missing: bool = True,
) -> str | None:
    """Return a Host.id for *ip_or_hostname* within *op_id*.

    Returns None if the input is not a plausible routable address/hostname,
    even when *create_if_missing* is True — we never auto-create hosts for
    multicast, reserved, unspecified, or non-hostname strings.

    If no host currently owns that IP/hostname:
    - If *create_if_missing* is True, creates a placeholder Host and returns
      its id.
    - Otherwise returns None.
    """
    ip = ip_or_hostname.strip()
    if not ip:
        return None
    if not _is_routable_address(ip):
        return None

    addr_type = _infer_addr_type(ip)

    # 1. Look for an exact HostIP match inside this op.
    #    For hostnames, match case-insensitively.
    if addr_type == "hostname":
        existing_ip = (
            db.query(HostIP)
            .join(Host, Host.id == HostIP.host_id)
            .filter(
                Host.op_id == op_id,
                HostIP.addr_type == "hostname",
                HostIP.ip_address.ilike(ip),
            )
            .first()
        )
    else:
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
        addr_type=addr_type,
        first_seen_at=datetime.now(timezone.utc),
    )
    db.add(host_ip)
    db.flush()

    return host_id
