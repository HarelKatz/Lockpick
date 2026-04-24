"""Unit tests for services/ip_resolver.py — resolve_ip()."""
import pytest
from sqlalchemy.orm import Session

from models import Host, HostIP, Operation
from services.ip_resolver import resolve_ip


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_op(db: Session, name: str = "Test Op") -> Operation:
    op = Operation(name=name)
    db.add(op)
    db.flush()
    return op


def _make_host(db: Session, op_id: str, nickname: str, ip: str | None = None) -> Host:
    host = Host(op_id=op_id, nickname=nickname)
    db.add(host)
    db.flush()
    if ip:
        db.add(HostIP(host_id=host.id, ip_address=ip))
        db.flush()
    return host


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_empty_string_returns_none(db_session):
    op = _make_op(db_session)
    result = resolve_ip(db_session, op.id, "")
    assert result is None


def test_whitespace_only_returns_none(db_session):
    op = _make_op(db_session)
    result = resolve_ip(db_session, op.id, "   ")
    assert result is None


def test_existing_ip_returns_host_id(db_session):
    op = _make_op(db_session)
    host = _make_host(db_session, op.id, "web01", ip="10.0.0.1")
    result = resolve_ip(db_session, op.id, "10.0.0.1")
    assert result == host.id


def test_existing_hostname_via_nickname(db_session):
    op = _make_op(db_session)
    host = _make_host(db_session, op.id, "web01")
    result = resolve_ip(db_session, op.id, "web01")
    assert result == host.id


def test_unknown_ip_create_if_missing_true(db_session):
    op = _make_op(db_session)
    result = resolve_ip(db_session, op.id, "192.168.1.99", create_if_missing=True)
    assert result is not None
    host = db_session.query(Host).filter_by(id=result).one()
    assert host is not None


def test_unknown_ip_create_if_missing_false(db_session):
    op = _make_op(db_session)
    result = resolve_ip(db_session, op.id, "192.168.1.99", create_if_missing=False)
    assert result is None
    count = db_session.query(Host).filter_by(op_id=op.id).count()
    assert count == 0


def test_new_host_nickname_is_ip_string(db_session):
    op = _make_op(db_session)
    ip_str = "10.10.10.10"
    host_id = resolve_ip(db_session, op.id, ip_str, create_if_missing=True)
    host = db_session.query(Host).filter_by(id=host_id).one()
    assert host.nickname == ip_str


def test_new_host_comment_text(db_session):
    op = _make_op(db_session)
    host_id = resolve_ip(db_session, op.id, "172.16.0.5", create_if_missing=True)
    host = db_session.query(Host).filter_by(id=host_id).one()
    assert host.comment == "Auto-created by parser (unresolved IP/hostname)"


def test_new_hostip_source_parsed(db_session):
    op = _make_op(db_session)
    host_id = resolve_ip(db_session, op.id, "10.1.2.3", create_if_missing=True)
    hip = db_session.query(HostIP).filter_by(host_id=host_id).one()
    assert hip.source == "parsed"


def test_cross_op_isolation(db_session):
    op_a = _make_op(db_session, name="Op A")
    op_b = _make_op(db_session, name="Op B")
    # Create a host in op_a with that IP
    _make_host(db_session, op_a.id, "hostA", ip="10.0.0.50")
    # Resolve in op_b — should NOT match op_a's host
    result = resolve_ip(db_session, op_b.id, "10.0.0.50", create_if_missing=True)
    # Result must be a new host in op_b, not op_a's host
    host = db_session.query(Host).filter_by(id=result).one()
    assert host.op_id == op_b.id


# ─── Priority 17: IPv6 address handling ──────────────────────────────────────

def test_ipv6_address_infers_addr_type(db_session):
    """resolve_ip with an IPv6 address must create a HostIP with addr_type='ipv6'."""
    from services.ip_resolver import _infer_addr_type
    assert _infer_addr_type("fe80::1") == "ipv6"
    assert _infer_addr_type("::1") == "ipv6"
    assert _infer_addr_type("2001:db8::1") == "ipv6"


def test_ipv4_address_infers_addr_type(db_session):
    from services.ip_resolver import _infer_addr_type
    assert _infer_addr_type("10.0.0.1") == "ipv4"
    assert _infer_addr_type("192.168.1.1") == "ipv4"


def test_hostname_infers_addr_type(db_session):
    from services.ip_resolver import _infer_addr_type
    assert _infer_addr_type("web01.corp") == "hostname"
    assert _infer_addr_type("localhost") == "hostname"


def test_ipv6_creates_host_with_correct_addr_type(db_session):
    """resolve_ip with IPv6 creates a HostIP with addr_type='ipv6'."""
    op = _make_op(db_session)
    host_id = resolve_ip(db_session, op.id, "fe80::1", create_if_missing=True)
    assert host_id is not None
    hip = db_session.query(HostIP).filter_by(host_id=host_id).one()
    assert hip.addr_type == "ipv6"
    assert hip.ip_address == "fe80::1"


def test_ipv6_existing_host_resolved(db_session):
    """resolve_ip for an already-stored IPv6 address returns the existing host."""
    op = _make_op(db_session)
    # Manually create a host with an IPv6 address
    host = Host(op_id=op.id, nickname="ipv6-host")
    db_session.add(host)
    db_session.flush()
    db_session.add(HostIP(host_id=host.id, ip_address="2001:db8::cafe",
                          source="manual", addr_type="ipv6"))
    db_session.flush()

    result = resolve_ip(db_session, op.id, "2001:db8::cafe")
    assert result == host.id


# ─── Priority 18: Hostname case-insensitive lookup ────────────────────────────

def test_hostname_lookup_case_insensitive(db_session):
    """resolve_ip('WEB01') must match an existing HostIP stored as 'web01'."""
    op = _make_op(db_session)
    host = Host(op_id=op.id, nickname="web01")
    db_session.add(host)
    db_session.flush()
    db_session.add(HostIP(host_id=host.id, ip_address="web01",
                          source="manual", addr_type="hostname"))
    db_session.flush()

    # Lookup with different case — must match the stored hostname
    result = resolve_ip(db_session, op.id, "WEB01")
    assert result == host.id, (
        f"Expected case-insensitive match for 'WEB01' → 'web01', got {result}"
    )


def test_hostname_lookup_uppercase_stored(db_session):
    """resolve_ip('web01') must match an existing HostIP stored as 'WEB01'."""
    op = _make_op(db_session)
    host = Host(op_id=op.id, nickname="WEB01")
    db_session.add(host)
    db_session.flush()
    db_session.add(HostIP(host_id=host.id, ip_address="WEB01",
                          source="manual", addr_type="hostname"))
    db_session.flush()

    result = resolve_ip(db_session, op.id, "web01")
    assert result == host.id
