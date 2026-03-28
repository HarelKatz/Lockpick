"""Unit tests for graph_builder service — calls build_graph/expand_host directly."""
import pytest
from sqlalchemy.orm import Session

from models import ConnectionRecord, Credential, CredentialLink, Host, HostIP, Operation
from services.graph_builder import build_graph, expand_host


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


def _make_cred(db: Session, op_id: str, fingerprint: str | None = None) -> Credential:
    cred = Credential(
        op_id=op_id,
        cred_type="private_key",
        value="-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----",
        fingerprint=fingerprint,
    )
    db.add(cred)
    db.flush()
    return cred


def _make_link(
    db: Session,
    cred_id: str,
    host_id: str,
    relationship: str,
    username: str | None = None,
) -> CredentialLink:
    link = CredentialLink(
        credential_id=cred_id,
        host_id=host_id,
        relationship_type=relationship,
        username=username,
    )
    db.add(link)
    db.flush()
    return link


def _make_conn(
    db: Session,
    op_id: str,
    src_host_id: str | None,
    dst_host_id: str | None,
    src_ip: str = "10.0.0.1",
    dst_ip: str = "10.0.0.2",
    direction_context: str = "from_dst_logs",
    source_file: str = "auth.log",
    credential_id: str | None = None,
) -> ConnectionRecord:
    conn = ConnectionRecord(
        op_id=op_id,
        src_host_id=src_host_id,
        src_ip=src_ip,
        dst_host_id=dst_host_id,
        dst_ip=dst_ip,
        direction_context=direction_context,
        source_file=source_file,
        connection_type="ssh",
        credential_id=credential_id,
    )
    db.add(conn)
    db.flush()
    return conn


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_empty_op_returns_empty_graph(db_session):
    op = _make_op(db_session)
    result = build_graph(db_session, op.id)
    assert result.nodes == []
    assert result.edges == []


def test_key_match_edge_confirmed(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    cred = _make_cred(db_session, op.id, fingerprint="SHA256:abc123")
    _make_link(db_session, cred.id, host_a.id, "found_on_disk", username="bob")
    _make_link(db_session, cred.id, host_b.id, "authorized_key", username="root")

    result = build_graph(db_session, op.id)

    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.src_host_id == host_a.id
    assert edge.dst_host_id == host_b.id
    assert edge.confidence == "confirmed"
    assert len(edge.evidence) == 1
    assert edge.evidence[0].type == "key_match"
    assert edge.evidence[0].confidence == "confirmed"
    assert edge.evidence[0].src_user == "bob"
    assert edge.evidence[0].dst_user == "root"


def test_null_fingerprint_no_key_match(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    cred = _make_cred(db_session, op.id, fingerprint=None)
    _make_link(db_session, cred.id, host_a.id, "found_on_disk")
    _make_link(db_session, cred.id, host_b.id, "authorized_key")

    result = build_graph(db_session, op.id)
    assert result.edges == []


def test_key_match_same_host_no_self_loop(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    cred = _make_cred(db_session, op.id, fingerprint="SHA256:loop")
    _make_link(db_session, cred.id, host_a.id, "found_on_disk")
    _make_link(db_session, cred.id, host_a.id, "authorized_key")

    result = build_graph(db_session, op.id)
    assert result.edges == []


def test_bash_history_indicator(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_src_logs",
        source_file=".bash_history",
    )

    result = build_graph(db_session, op.id)
    assert len(result.edges) == 1
    ev = result.edges[0].evidence[0]
    assert ev.type == "bash_history"
    assert ev.confidence == "indicator"
    assert result.edges[0].confidence == "indicator"


def test_known_hosts_indicator(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_src_logs",
        source_file="known_hosts",
    )

    result = build_graph(db_session, op.id)
    assert len(result.edges) == 1
    ev = result.edges[0].evidence[0]
    assert ev.type == "known_hosts"
    assert ev.confidence == "indicator"


def test_dst_logs_with_cred_confirmed(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    cred = _make_cred(db_session, op.id)
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_dst_logs",
        source_file="auth.log",
        credential_id=cred.id,
    )

    result = build_graph(db_session, op.id)
    assert len(result.edges) == 1
    ev = result.edges[0].evidence[0]
    assert ev.type == "connection_log"
    assert ev.confidence == "confirmed"


def test_dst_logs_no_cred_observed(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_dst_logs",
        source_file="auth.log",
    )

    result = build_graph(db_session, op.id)
    assert len(result.edges) == 1
    ev = result.edges[0].evidence[0]
    assert ev.type == "connection_log"
    assert ev.confidence == "observed"


def test_src_logs_observed(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_src_logs",
        source_file="manual",
    )

    result = build_graph(db_session, op.id)
    assert len(result.edges) == 1
    ev = result.edges[0].evidence[0]
    assert ev.type == "connection_log"
    assert ev.confidence == "observed"


def test_max_confidence_wins(db_session):
    """Key_match + bash_history on same pair → edge confidence is confirmed."""
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")

    # bash_history indicator
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_src_logs",
        source_file=".bash_history",
    )

    # key match confirmed
    cred = _make_cred(db_session, op.id, fingerprint="SHA256:maxconf")
    _make_link(db_session, cred.id, host_a.id, "found_on_disk", username="alice")
    _make_link(db_session, cred.id, host_b.id, "authorized_key", username="root")

    result = build_graph(db_session, op.id)
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.confidence == "confirmed"
    assert len(edge.evidence) == 2


def test_host_ids_filter(db_session):
    """Only edges between the requested host subset are returned."""
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    host_c = _make_host(db_session, op.id, "hostC")

    cred = _make_cred(db_session, op.id, fingerprint="SHA256:filter")
    _make_link(db_session, cred.id, host_a.id, "found_on_disk")
    _make_link(db_session, cred.id, host_b.id, "authorized_key")
    _make_link(db_session, cred.id, host_c.id, "authorized_key")

    # Request only A and C — should see A→C edge, not A→B
    result = build_graph(db_session, op.id, host_ids=[host_a.id, host_c.id])
    assert len(result.nodes) == 2
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.src_host_id == host_a.id
    assert edge.dst_host_id == host_c.id


def test_null_host_id_excluded(db_session):
    """ConnectionRecords with null src/dst host_id are not included as edges."""
    op = _make_op(db_session)
    host_b = _make_host(db_session, op.id, "hostB")
    # src_host_id is None
    _make_conn(db_session, op.id, None, host_b.id, source_file="auth.log")

    result = build_graph(db_session, op.id)
    assert result.edges == []


def test_expand_host_returns_neighbors(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    host_c = _make_host(db_session, op.id, "hostC")

    cred_ab = _make_cred(db_session, op.id, fingerprint="SHA256:ab")
    _make_link(db_session, cred_ab.id, host_a.id, "found_on_disk")
    _make_link(db_session, cred_ab.id, host_b.id, "authorized_key")

    # host_c is unrelated
    _make_conn(db_session, op.id, host_b.id, host_c.id, source_file="auth.log")

    result = expand_host(db_session, op.id, host_a.id)
    node_ids = {n.host_id for n in result.nodes}
    # Should include A and B (adjacent via key match), but not C
    assert host_a.id in node_ids
    assert host_b.id in node_ids
    assert host_c.id not in node_ids
    assert len(result.edges) == 1


def test_expand_host_evidence_type_filter(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")

    # Both a key_match and a connection_log exist
    cred = _make_cred(db_session, op.id, fingerprint="SHA256:ef")
    _make_link(db_session, cred.id, host_a.id, "found_on_disk")
    _make_link(db_session, cred.id, host_b.id, "authorized_key")
    _make_conn(db_session, op.id, host_a.id, host_b.id, source_file="auth.log")

    # Filter to key_match only
    result = expand_host(db_session, op.id, host_a.id, evidence_type="key_match")
    assert len(result.edges) == 1
    assert all(e.type == "key_match" for e in result.edges[0].evidence)

    # Filter to connection_log only
    result2 = expand_host(db_session, op.id, host_a.id, evidence_type="connection_log")
    assert len(result2.edges) == 1
    assert all(e.type == "connection_log" for e in result2.edges[0].evidence)
