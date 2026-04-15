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
