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
    parser_file_type: str | None = None,
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
        parser_file_type=parser_file_type,
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


def test_arp_indicator(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_src_logs",
        source_file="arp_dump.txt",
        parser_file_type="arp",
    )

    result = build_graph(db_session, op.id)
    assert len(result.edges) == 1
    ev = result.edges[0].evidence[0]
    assert ev.type == "arp"
    assert ev.confidence == "indicator"


def test_ip_neigh_indicator(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_src_logs",
        source_file="ip_neigh.out",
        parser_file_type="ip_neigh",
    )

    result = build_graph(db_session, op.id)
    assert len(result.edges) == 1
    ev = result.edges[0].evidence[0]
    assert ev.type == "ip_neigh"
    assert ev.confidence == "indicator"


def test_iptables_indicator(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_src_logs",
        source_file="iptables.save",
        parser_file_type="iptables",
    )

    result = build_graph(db_session, op.id)
    assert len(result.edges) == 1
    ev = result.edges[0].evidence[0]
    assert ev.type == "iptables"
    assert ev.confidence == "indicator"


def test_nftables_indicator(db_session):
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_src_logs",
        source_file="nft.list",
        parser_file_type="nftables",
    )

    result = build_graph(db_session, op.id)
    assert len(result.edges) == 1
    ev = result.edges[0].evidence[0]
    assert ev.type == "nftables"
    assert ev.confidence == "indicator"


def test_parser_file_type_wins_over_legacy_substring(db_session):
    """parser_file_type is authoritative; substring match in source_file is ignored when column is set."""
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_src_logs",
        source_file="bash_history.txt",   # would match legacy fallback
        parser_file_type="arp",            # but column wins
    )

    result = build_graph(db_session, op.id)
    ev = result.edges[0].evidence[0]
    assert ev.type == "arp"
    assert ev.confidence == "indicator"


def test_non_indicator_parser_file_type_falls_through(db_session):
    """A parser_file_type not in _INDICATOR_PARSER_TYPES does not auto-promote to indicator."""
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_dst_logs",
        source_file="auth.log",
        parser_file_type="auth_log",
    )

    result = build_graph(db_session, op.id)
    ev = result.edges[0].evidence[0]
    assert ev.type == "connection_log"
    assert ev.confidence == "observed"


def test_legacy_null_parser_file_type_falls_back_to_source_file(db_session):
    """Rows persisted before the column existed (parser_file_type IS NULL) keep classifying via source_file substring."""
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")
    _make_conn(
        db_session, op.id, host_a.id, host_b.id,
        direction_context="from_src_logs",
        source_file=".bash_history",
        parser_file_type=None,
    )

    result = build_graph(db_session, op.id)
    ev = result.edges[0].evidence[0]
    assert ev.type == "bash_history"
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


# ─── Priority 9: expand_host indicator evidence_type filter ───────────────────

def test_expand_host_indicator_filter(db_session):
    """expand_host(evidence_type='indicator') returns only indicator edges."""
    op = _make_op(db_session)
    host_a = _make_host(db_session, op.id, "hostA")
    host_b = _make_host(db_session, op.id, "hostB")

    # bash_history (indicator) + auth.log (observed) connection
    _make_conn(db_session, op.id, host_a.id, host_b.id,
               direction_context="from_src_logs", source_file=".bash_history")
    _make_conn(db_session, op.id, host_a.id, host_b.id,
               direction_context="from_dst_logs", source_file="auth.log")

    result = expand_host(db_session, op.id, host_a.id, evidence_type="indicator")
    # The indicator filter should only return bash_history evidence
    assert len(result.edges) == 1
    for ev in result.edges[0].evidence:
        assert ev.type in ("bash_history", "known_hosts"), (
            f"Expected indicator evidence type, got {ev.type}"
        )


# ─── Priority 19: _max_confidence([]) guard ───────────────────────────────────

def test_max_confidence_with_single_item():
    """_max_confidence works correctly with a single-element list."""
    from services.graph_builder import _max_confidence
    assert _max_confidence(["confirmed"]) == "confirmed"
    assert _max_confidence(["observed"]) == "observed"
    assert _max_confidence(["indicator"]) == "indicator"


def test_max_confidence_returns_highest():
    """_max_confidence returns the highest-ranked confidence from mixed list."""
    from services.graph_builder import _max_confidence
    assert _max_confidence(["indicator", "confirmed", "observed"]) == "confirmed"
    assert _max_confidence(["indicator", "observed"]) == "observed"
    assert _max_confidence(["indicator", "indicator"]) == "indicator"


def test_max_confidence_empty_list_raises():
    """_max_confidence([]) raises ValueError (documents the known gap — no empty guard).

    NOTE: This test documents BUG-10 from the audit: _max_confidence has no guard
    against an empty list. The builtin max() raises ValueError on empty input.
    The caller (build_graph edge aggregation) never passes an empty list in practice
    because edges only exist when there is at least one evidence item. However, if
    called directly with an empty list, it will raise ValueError.
    """
    from services.graph_builder import _max_confidence
    # Document the known behavior: empty list raises ValueError
    with pytest.raises(ValueError):
        _max_confidence([])
