"""Property/invariant tests for the pure + ORM-level services.

Style A: call the service directly against raw ORM rows / the shared session.
Covers ``ssh_match`` (glob semantics), ``_classify_connection_evidence`` (priority),
``resolve_ip`` (rejection), and ``merge_hosts`` (dedup + source deletion).
"""
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from models import (
    ConnectionRecord,
    Credential,
    CredentialLink,
    Host,
    HostIP,
    Operation,
)
from services.graph_builder import _classify_connection_evidence
from services.host_merge import merge_hosts
from services.ip_resolver import resolve_ip
from services.ssh_pattern import ssh_match
from tests.opbuilder import OpBuilder
from tests.test_invariants.strategies import structure_topologies

pytestmark = pytest.mark.property

# Hostname-ish alphabet with NO fnmatch metacharacters (*, ?, [, !) so a drawn
# name is always a literal pattern (and a valid candidate).
_NAME = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-", min_size=1, max_size=24)


# ── ssh_match: man-5 ssh_config glob semantics ──────────────────────────────

@given(name=_NAME)
def test_ssh_match_literal_self_match(name):
    assert ssh_match(name, [name]) is True


@given(name=_NAME)
def test_ssh_match_wildcard_matches_anything(name):
    assert ssh_match(name, ["*"]) is True


@given(name=_NAME)
def test_ssh_match_negation_vetoes_positive_star(name):
    # `*` matches, but the explicit `!name` negation must veto it.
    assert ssh_match(name, ["*", f"!{name}"]) is False


@given(name=_NAME)
def test_ssh_match_is_case_insensitive(name):
    assert ssh_match(name.upper(), [name.lower()]) is True


# ── _classify_connection_evidence: priority order ───────────────────────────

def _conn(**kw) -> ConnectionRecord:
    base = dict(src_ip="10.0.0.1", dst_ip="10.0.0.2", source_file="x",
                direction_context="from_dst_logs")
    base.update(kw)
    return ConnectionRecord(**base)


def test_classify_indicator_parser_type_beats_confirmed():
    # An indicator parser type wins even when from_dst_logs + a credential would
    # otherwise classify as confirmed.
    rec = _conn(parser_file_type="known_hosts", credential_id="c1")
    assert _classify_connection_evidence(rec) == ("known_hosts", "indicator")


def test_classify_confirmed_needs_dst_logs_and_credential():
    rec = _conn(direction_context="from_dst_logs", credential_id="c1")
    assert _classify_connection_evidence(rec) == ("connection_log", "confirmed")


def test_classify_defaults_to_observed():
    rec = _conn(direction_context="from_src_logs")
    assert _classify_connection_evidence(rec) == ("connection_log", "observed")


def test_classify_legacy_source_file_substring_is_indicator():
    rec = _conn(source_file="user_bash_history", credential_id="c1")
    assert _classify_connection_evidence(rec) == ("bash_history", "indicator")


# ── resolve_ip: rejects non-routable, accepts routable ──────────────────────

def _make_op(db: Session) -> Operation:
    op = Operation(name="inv")
    db.add(op)
    db.flush()
    return op


@given(ip=st.ip_addresses())
def test_resolve_ip_rejects_iff_non_routable(db_session, ip):
    op = _make_op(db_session)
    non_routable = ip.is_multicast or ip.is_reserved or ip.is_unspecified
    result = resolve_ip(db_session, op.id, str(ip), create_if_missing=True)
    if non_routable:
        assert result is None
        assert db_session.query(Host).filter(Host.op_id == op.id).count() == 0
    else:
        assert result is not None


# ── merge_hosts: dedup + source deletion ────────────────────────────────────

def test_merge_dedups_and_deletes_source(db_session):
    """Reliable break-to-fail for the dedup guard: same IP and same credential-link
    key on both sides must collapse to one on the target, and source must vanish."""
    op = _make_op(db_session)
    src = Host(op_id=op.id, nickname="src")
    tgt = Host(op_id=op.id, nickname="tgt")
    db_session.add_all([src, tgt])
    db_session.flush()
    db_session.add(HostIP(host_id=src.id, ip_address="10.0.0.9"))
    db_session.add(HostIP(host_id=tgt.id, ip_address="10.0.0.9"))
    cred = Credential(op_id=op.id, cred_type="password", value="pw")
    db_session.add(cred)
    db_session.flush()
    for h in (src, tgt):
        db_session.add(CredentialLink(
            credential_id=cred.id, host_id=h.id,
            username="root", relationship_type="accepted_password",
        ))
    db_session.flush()

    merge_hosts(db_session, op.id, src.id, tgt.id)
    db_session.flush()

    assert db_session.query(Host).filter(Host.id == src.id).first() is None
    ips = [r.ip_address for r in db_session.query(HostIP).filter(HostIP.host_id == tgt.id)]
    assert ips == ["10.0.0.9"]
    links = db_session.query(CredentialLink).filter(CredentialLink.host_id == tgt.id).all()
    assert len(links) == 1


@given(topo=structure_topologies(min_hosts=3, max_hosts=15))
def test_merge_preserves_structure(client, db_session, topo):
    """Over any generated op: merging two hosts deletes the source, never leaves a
    duplicate IP / credential-link on the target, and loses no connection."""
    lo = OpBuilder(client).apply_topology(topo)
    ids = list(lo.host_ids.values())
    src_id, tgt_id = ids[0], ids[1]
    before = db_session.query(ConnectionRecord).filter(ConnectionRecord.op_id == lo.op_id).count()

    merge_hosts(db_session, lo.op_id, src_id, tgt_id)
    db_session.flush()

    assert db_session.query(Host).filter(Host.id == src_id).first() is None
    tgt_ips = [r.ip_address for r in db_session.query(HostIP).filter(HostIP.host_id == tgt_id)]
    assert len(tgt_ips) == len(set(tgt_ips))
    keys = [(l.credential_id, l.relationship_type, l.username)
            for l in db_session.query(CredentialLink).filter(CredentialLink.host_id == tgt_id)]
    assert len(keys) == len(set(keys))
    after = db_session.query(ConnectionRecord).filter(ConnectionRecord.op_id == lo.op_id).count()
    assert after == before
