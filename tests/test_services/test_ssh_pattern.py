"""Unit tests for services/ssh_pattern.py — ssh_match() glob semantics."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from models import ConnectionRecord, Host, HostIP, Operation, SshConfigPattern
from services.ssh_pattern import apply_patterns_to_host, ssh_match


# ─── Exact matches ────────────────────────────────────────────────────────────

def test_exact_ip_matches():
    assert ssh_match("10.0.0.1", ["10.0.0.1"])


def test_exact_ip_no_match():
    assert not ssh_match("10.0.0.2", ["10.0.0.1"])


def test_exact_hostname_matches():
    assert ssh_match("jumpbox.corp", ["jumpbox.corp"])


# ─── Wildcard * ───────────────────────────────────────────────────────────────

def test_wildcard_matches_any_string():
    assert ssh_match("anything.corp", ["*.corp"])


def test_wildcard_star_alone_matches_all():
    assert ssh_match("10.0.0.1", ["*"])
    assert ssh_match("some-host", ["*"])


def test_wildcard_prefix():
    assert ssh_match("dev-box", ["dev-*"])


def test_wildcard_no_match():
    assert not ssh_match("prod.example.com", ["dev.*"])


# ─── Single-char wildcard ? ───────────────────────────────────────────────────

def test_question_mark_matches_one_char():
    assert ssh_match("host1", ["host?"])


def test_question_mark_does_not_match_multiple():
    assert not ssh_match("host12", ["host?"])


# ─── Negation ─────────────────────────────────────────────────────────────────

def test_negation_excludes_match():
    assert not ssh_match("jb.corp", ["*.corp", "!jb.corp"])


def test_negation_allows_other_hosts():
    assert ssh_match("other.corp", ["*.corp", "!jb.corp"])


def test_negation_with_wildcard():
    assert not ssh_match("internal.corp", ["*", "!internal.corp"])


def test_negation_only_list_never_matches():
    """No positive patterns → nothing should match."""
    assert not ssh_match("10.0.0.1", ["!10.0.0.1"])
    assert not ssh_match("anything", ["!other"])


# ─── Case-insensitivity ───────────────────────────────────────────────────────

def test_case_insensitive_candidate():
    assert ssh_match("JUMPBOX.CORP", ["jumpbox.corp"])


def test_case_insensitive_pattern():
    assert ssh_match("jumpbox.corp", ["JUMPBOX.CORP"])


def test_case_insensitive_wildcard():
    assert ssh_match("JB.CORP", ["jb.*"])


def test_case_insensitive_negation():
    assert not ssh_match("JB.CORP", ["*.corp", "!JB.CORP"])


# ─── Multiple positive patterns (any match is enough) ─────────────────────────

def test_multiple_positives_first_matches():
    assert ssh_match("db01", ["db*", "web*"])


def test_multiple_positives_second_matches():
    assert ssh_match("web01", ["db*", "web*"])


def test_multiple_positives_none_match():
    assert not ssh_match("app01", ["db*", "web*"])


# ─── Edge cases ───────────────────────────────────────────────────────────────

def test_empty_aliases_never_matches():
    assert not ssh_match("anything", [])


def test_empty_candidate_with_star():
    assert ssh_match("", ["*"])


def test_empty_candidate_exact_no_match():
    assert not ssh_match("", ["host"])


# ─── Priority 4: apply_patterns_to_host unit tests ───────────────────────────


def _mk_op(db):
    op = Operation(name="pat-test")
    db.add(op)
    db.flush()
    return op


def _mk_host(db, op_id, nickname, ip=None):
    host = Host(op_id=op_id, nickname=nickname)
    db.add(host)
    db.flush()
    if ip:
        db.add(HostIP(host_id=host.id, ip_address=ip, addr_type="ipv4"))
        db.flush()
    return host


def _mk_pattern(db, op_id, source_host_id, pattern, username=None):
    pat = SshConfigPattern(
        op_id=op_id,
        source_host_id=source_host_id,
        pattern=pattern,
        username=username,
    )
    db.add(pat)
    db.flush()
    return pat


def test_apply_patterns_creates_connection_for_match(db_session):
    """A matching pattern→host pair creates exactly one ConnectionRecord."""
    db = db_session
    op = _mk_op(db)
    src = _mk_host(db, op.id, "src-host", ip="10.0.0.1")
    _mk_pattern(db, op.id, src.id, "*.corp")

    # New host with a name matching the pattern
    new_host = _mk_host(db, op.id, "web.corp", ip="10.0.0.2")

    count = apply_patterns_to_host(db, new_host)
    assert count == 1

    # Flush so pending records are visible to queries (session has autoflush=False)
    db.flush()

    # Verify the ConnectionRecord was created
    records = db.query(ConnectionRecord).filter(
        ConnectionRecord.op_id == op.id,
        ConnectionRecord.src_host_id == src.id,
        ConnectionRecord.dst_host_id == new_host.id,
    ).all()
    assert len(records) == 1
    assert records[0].source_file == "ssh_config_pattern"
    assert records[0].direction_context == "from_src_logs"


def test_apply_patterns_no_duplicate_on_second_call(db_session):
    """Calling apply_patterns_to_host twice for the same host must not create duplicates."""
    db = db_session
    op = _mk_op(db)
    src = _mk_host(db, op.id, "src-host", ip="10.0.0.1")
    _mk_pattern(db, op.id, src.id, "*.corp")
    new_host = _mk_host(db, op.id, "web.corp", ip="10.0.0.2")

    count1 = apply_patterns_to_host(db, new_host)
    # Flush after first call so the dedup query in second call can see the record
    db.flush()
    count2 = apply_patterns_to_host(db, new_host)
    assert count1 == 1
    assert count2 == 0  # dedup: no new record created

    db.flush()
    total = db.query(ConnectionRecord).filter(
        ConnectionRecord.op_id == op.id,
        ConnectionRecord.src_host_id == src.id,
        ConnectionRecord.dst_host_id == new_host.id,
    ).count()
    assert total == 1


def test_apply_patterns_no_match_creates_nothing(db_session):
    """A host whose name does not match the pattern creates no ConnectionRecord."""
    db = db_session
    op = _mk_op(db)
    src = _mk_host(db, op.id, "src-host", ip="10.0.0.1")
    _mk_pattern(db, op.id, src.id, "*.corp")
    non_matching = _mk_host(db, op.id, "prod.example.com", ip="10.0.0.2")

    count = apply_patterns_to_host(db, non_matching)
    assert count == 0
    assert db.query(ConnectionRecord).filter(ConnectionRecord.op_id == op.id).count() == 0


def test_apply_patterns_self_loop_prevented(db_session):
    """Pattern source host must not create a ConnectionRecord to itself."""
    db = db_session
    op = _mk_op(db)
    src = _mk_host(db, op.id, "jb.corp", ip="10.0.0.1")
    _mk_pattern(db, op.id, src.id, "*.corp")  # pattern matches "jb.corp"

    # Call apply_patterns for the source host itself
    count = apply_patterns_to_host(db, src)
    assert count == 0
    assert db.query(ConnectionRecord).count() == 0
