"""Unit tests for services/ip_resolver.py — resolve_ip(), is_unresolved_host()."""
import pytest
from sqlalchemy.orm import Session, selectinload

from models import (
    Credential,
    CredentialLink,
    Host,
    HostIP,
    HostNote,
    HostUser,
    Operation,
    SudoRule,
)
from services.ip_resolver import AUTO_CREATED_COMMENT, is_unresolved_host, resolve_ip


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


# ─── Non-routable / invalid inputs ────────────────────────────────────────────

@pytest.mark.parametrize(
    "bad_input",
    [
        # IPv6 multicast / link-local / reserved — commonly in /etc/hosts on Linux
        "ff00::0",
        "ff02::1",
        "ff02::2",
        "fe00::0",
        # IPv4 multicast + broadcast + unspecified + reserved
        "224.0.0.1",
        "239.255.255.255",
        "255.255.255.255",
        "0.0.0.0",
        "240.0.0.1",
        # utmp-style magic that doesn't look like a hostname
        "~",
        # Shell-like garbage
        "not a hostname with spaces",
        "(command: ip addr)",
    ],
)
def test_non_routable_inputs_are_rejected(db_session, bad_input):
    """resolve_ip must never auto-create hosts for multicast / reserved /
    non-hostname inputs. Bad inputs leak in from /etc/hosts and wtmp."""
    op = _make_op(db_session)
    result = resolve_ip(db_session, op.id, bad_input, create_if_missing=True)
    assert result is None, f"Expected None for {bad_input!r}, got {result}"
    # No phantom host should have been created
    assert db_session.query(Host).filter(Host.op_id == op.id).count() == 0


def test_valid_ipv4_still_resolved(db_session):
    op = _make_op(db_session)
    result = resolve_ip(db_session, op.id, "10.0.0.5", create_if_missing=True)
    assert result is not None
    assert db_session.query(Host).filter(Host.op_id == op.id).count() == 1


def test_valid_hostname_still_resolved(db_session):
    op = _make_op(db_session)
    result = resolve_ip(db_session, op.id, "web01.corp.local", create_if_missing=True)
    assert result is not None


def test_unique_local_ipv6_still_resolved(db_session):
    """fc00::/7 (unique local) is routable within an org — must not be rejected."""
    op = _make_op(db_session)
    result = resolve_ip(db_session, op.id, "fd12:3456::1", create_if_missing=True)
    assert result is not None


# ─── is_unresolved_host predicate ─────────────────────────────────────────────

def _eager_host(db: Session, host_id: str) -> Host:
    """Re-fetch a host with the four relationships is_unresolved_host requires."""
    return (
        db.query(Host)
        .options(
            selectinload(Host.users),
            selectinload(Host.credential_links),
            selectinload(Host.notes),
            selectinload(Host.sudo_rules),
        )
        .filter(Host.id == host_id)
        .one()
    )


def _placeholder(db: Session, op_id: str, ip: str) -> Host:
    """Create a placeholder host the way resolve_ip does, so the auto-created
    comment marker is in place."""
    host_id = resolve_ip(db, op_id, ip, create_if_missing=True)
    return db.query(Host).filter(Host.id == host_id).one()


def test_is_unresolved_host_pure_placeholder(db_session):
    """A bare placeholder (auto-created marker, only IPs) is unresolved."""
    op = _make_op(db_session)
    host = _placeholder(db_session, op.id, "10.0.0.1")
    assert is_unresolved_host(_eager_host(db_session, host.id)) is True


def test_is_unresolved_host_user_created_returns_false(db_session):
    """A host the operator created (no auto-marker comment) is NOT unresolved
    even when it has zero relations attached."""
    op = _make_op(db_session)
    host = _make_host(db_session, op.id, "web01", ip="10.0.0.5")
    # _make_host leaves comment=None — like a manual POST /hosts.
    assert is_unresolved_host(_eager_host(db_session, host.id)) is False


def test_is_unresolved_host_with_user_returns_false(db_session):
    op = _make_op(db_session)
    host = _placeholder(db_session, op.id, "10.0.0.5")
    db_session.add(HostUser(host_id=host.id, username="root"))
    db_session.flush()
    assert is_unresolved_host(_eager_host(db_session, host.id)) is False


def test_is_unresolved_host_with_credential_link_returns_false(db_session):
    op = _make_op(db_session)
    host = _placeholder(db_session, op.id, "10.0.0.5")
    cred = Credential(op_id=op.id, cred_type="password", value="hunter2")
    db_session.add(cred)
    db_session.flush()
    db_session.add(CredentialLink(
        credential_id=cred.id, host_id=host.id,
        username="root", relationship_type="accepted_password",
    ))
    db_session.flush()
    assert is_unresolved_host(_eager_host(db_session, host.id)) is False


def test_is_unresolved_host_with_note_returns_false(db_session):
    op = _make_op(db_session)
    host = _placeholder(db_session, op.id, "10.0.0.5")
    db_session.add(HostNote(op_id=op.id, host_id=host.id, content="Operator note"))
    db_session.flush()
    assert is_unresolved_host(_eager_host(db_session, host.id)) is False


def test_is_unresolved_host_with_sudo_rule_returns_false(db_session):
    op = _make_op(db_session)
    host = _placeholder(db_session, op.id, "10.0.0.5")
    db_session.add(SudoRule(
        host_id=host.id, op_id=op.id,
        subject="alice", subject_type="user",
        run_as="root", commands="ALL", nopasswd=False,
    ))
    db_session.flush()
    assert is_unresolved_host(_eager_host(db_session, host.id)) is False


def test_is_unresolved_host_with_multiple_ips_still_true(db_session):
    """Several parsed HostIPs on a placeholder, no other content → still unresolved."""
    op = _make_op(db_session)
    host = _placeholder(db_session, op.id, "10.0.0.1")
    db_session.add(HostIP(host_id=host.id, ip_address="db1.corp",
                          source="parsed", addr_type="hostname"))
    db_session.add(HostIP(host_id=host.id, ip_address="10.0.0.2",
                          source="parsed", addr_type="ipv4"))
    db_session.flush()
    assert is_unresolved_host(_eager_host(db_session, host.id)) is True


def test_is_unresolved_host_edited_comment_returns_false(db_session):
    """Operator edited the comment — host is no longer 'auto-created' from our view."""
    op = _make_op(db_session)
    host = _placeholder(db_session, op.id, "10.0.0.1")
    host.comment = "Lead jump box for cluster"
    db_session.flush()
    assert is_unresolved_host(_eager_host(db_session, host.id)) is False


def test_auto_created_comment_constant_matches_what_resolve_ip_writes(db_session):
    """The placeholder we just created carries the canonical marker."""
    op = _make_op(db_session)
    host = _placeholder(db_session, op.id, "10.0.0.1")
    assert host.comment == AUTO_CREATED_COMMENT
