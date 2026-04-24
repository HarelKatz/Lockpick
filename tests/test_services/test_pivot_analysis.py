"""Unit tests for services/pivot_analysis.py — find_paths()."""
import pytest
from sqlalchemy.orm import Session

from models import ConnectionRecord, Credential, CredentialLink, Host, HostIP, Operation
from schemas import PathFinderRequest, WaypointConstraint
from services.pivot_analysis import find_paths


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


# ─── Helper: key-match edge between two hosts ─────────────────────────────────

def _make_key_edge(db: Session, op_id: str, src: Host, dst: Host, fp: str) -> None:
    cred = _make_cred(db, op_id, fingerprint=fp)
    _make_link(db, cred.id, src.id, "found_on_disk", username="user")
    _make_link(db, cred.id, dst.id, "authorized_key", username="root")


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_src_equals_dst_returns_empty(db_session):
    op = _make_op(db_session)
    host = _make_host(db_session, op.id, "hostA")
    req = PathFinderRequest(src_host_id=host.id, dst_host_id=host.id, mode="shortest")
    resp = find_paths(db_session, op.id, req)
    assert resp.paths == []
    assert resp.truncated is False


def test_no_path_disconnected_hosts(db_session):
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "srcHost")
    dst = _make_host(db_session, op.id, "dstHost")
    req = PathFinderRequest(src_host_id=src.id, dst_host_id=dst.id, mode="shortest")
    resp = find_paths(db_session, op.id, req)
    assert resp.paths == []
    assert resp.truncated is False


def test_simple_two_hop_key_match(db_session):
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    dst = _make_host(db_session, op.id, "dst")
    _make_key_edge(db_session, op.id, src, dst, fp="SHA256:simple")
    req = PathFinderRequest(src_host_id=src.id, dst_host_id=dst.id, mode="shortest")
    resp = find_paths(db_session, op.id, req)
    assert len(resp.paths) == 1
    assert resp.paths[0].host_ids == [src.id, dst.id]


def test_three_hop_shortest_mode(db_session):
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    hop = _make_host(db_session, op.id, "hop")
    dst = _make_host(db_session, op.id, "dst")
    _make_conn(db_session, op.id, src.id, hop.id, src_ip="1.1.1.1", dst_ip="1.1.1.2")
    _make_conn(db_session, op.id, hop.id, dst.id, src_ip="1.1.1.2", dst_ip="1.1.1.3")
    req = PathFinderRequest(src_host_id=src.id, dst_host_id=dst.id, mode="shortest")
    resp = find_paths(db_session, op.id, req)
    assert len(resp.paths) == 1
    assert resp.paths[0].host_ids == [src.id, hop.id, dst.id]


def test_all_mode_returns_multiple_paths(db_session):
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    hop1 = _make_host(db_session, op.id, "hop1")
    hop2 = _make_host(db_session, op.id, "hop2")
    dst = _make_host(db_session, op.id, "dst")
    _make_conn(db_session, op.id, src.id, hop1.id, src_ip="1.0.0.1", dst_ip="1.0.0.2")
    _make_conn(db_session, op.id, hop1.id, dst.id, src_ip="1.0.0.2", dst_ip="1.0.0.4")
    _make_conn(db_session, op.id, src.id, hop2.id, src_ip="1.0.0.1", dst_ip="1.0.0.3")
    _make_conn(db_session, op.id, hop2.id, dst.id, src_ip="1.0.0.3", dst_ip="1.0.0.4")
    req = PathFinderRequest(src_host_id=src.id, dst_host_id=dst.id, mode="all")
    resp = find_paths(db_session, op.id, req)
    assert len(resp.paths) == 2
    path_hops = {tuple(p.host_ids[1:-1]) for p in resp.paths}
    assert (hop1.id,) in path_hops
    assert (hop2.id,) in path_hops


def test_max_depth_9_hops_excluded(db_session):
    """A 10-host chain (9 hops) must be excluded because _MAX_DEPTH == 8."""
    op = _make_op(db_session)
    hosts = [_make_host(db_session, op.id, f"h{i}") for i in range(10)]
    for i in range(9):
        _make_conn(
            db_session, op.id, hosts[i].id, hosts[i + 1].id,
            src_ip=f"10.0.0.{i}", dst_ip=f"10.0.0.{i+1}",
        )
    req = PathFinderRequest(src_host_id=hosts[0].id, dst_host_id=hosts[9].id, mode="shortest")
    resp = find_paths(db_session, op.id, req)
    assert resp.paths == []


def test_max_depth_8_hops_included(db_session):
    """A 9-host chain (8 hops) is exactly at the limit and must be returned."""
    op = _make_op(db_session)
    hosts = [_make_host(db_session, op.id, f"h{i}") for i in range(9)]
    for i in range(8):
        _make_conn(
            db_session, op.id, hosts[i].id, hosts[i + 1].id,
            src_ip=f"10.1.0.{i}", dst_ip=f"10.1.0.{i+1}",
        )
    req = PathFinderRequest(src_host_id=hosts[0].id, dst_host_id=hosts[8].id, mode="shortest")
    resp = find_paths(db_session, op.id, req)
    assert len(resp.paths) == 1
    assert len(resp.paths[0].host_ids) == 9


def test_truncation_over_30_paths(db_session):
    """31 intermediaries src→hop_i→dst with mode='all' → 30 paths, truncated==True."""
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    dst = _make_host(db_session, op.id, "dst")
    for i in range(31):
        hop = _make_host(db_session, op.id, f"hop{i}")
        _make_conn(
            db_session, op.id, src.id, hop.id,
            src_ip="10.2.0.0", dst_ip=f"10.2.1.{i % 256}",
        )
        _make_conn(
            db_session, op.id, hop.id, dst.id,
            src_ip=f"10.2.1.{i % 256}", dst_ip="10.2.0.1",
        )
    req = PathFinderRequest(src_host_id=src.id, dst_host_id=dst.id, mode="all")
    resp = find_paths(db_session, op.id, req)
    assert len(resp.paths) == 30
    assert resp.truncated is True


def test_waypoint_anywhere(db_session):
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    hop = _make_host(db_session, op.id, "hop")
    other = _make_host(db_session, op.id, "other")
    dst = _make_host(db_session, op.id, "dst")

    # Path through hop
    _make_conn(db_session, op.id, src.id, hop.id, src_ip="10.3.0.0", dst_ip="10.3.0.1")
    _make_conn(db_session, op.id, hop.id, dst.id, src_ip="10.3.0.1", dst_ip="10.3.0.2")
    # Direct path (bypasses hop)
    _make_conn(db_session, op.id, src.id, other.id, src_ip="10.3.0.0", dst_ip="10.3.0.3")
    _make_conn(db_session, op.id, other.id, dst.id, src_ip="10.3.0.3", dst_ip="10.3.0.2")

    req = PathFinderRequest(
        src_host_id=src.id,
        dst_host_id=dst.id,
        mode="all",
        waypoints=[WaypointConstraint(host_id=hop.id, position="anywhere")],
    )
    resp = find_paths(db_session, op.id, req)
    assert len(resp.paths) == 1
    assert hop.id in resp.paths[0].host_ids


def test_waypoint_after_no_relative_to(db_session):
    """Waypoint position='after' with no relative_to: waypoint must be first hop after src."""
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    hop = _make_host(db_session, op.id, "hop")
    other = _make_host(db_session, op.id, "other")
    dst = _make_host(db_session, op.id, "dst")

    # src → hop → dst (hop is first after src)
    _make_conn(db_session, op.id, src.id, hop.id, src_ip="10.4.0.0", dst_ip="10.4.0.1")
    _make_conn(db_session, op.id, hop.id, dst.id, src_ip="10.4.0.1", dst_ip="10.4.0.3")
    # src → other → dst (other is first after src)
    _make_conn(db_session, op.id, src.id, other.id, src_ip="10.4.0.0", dst_ip="10.4.0.2")
    _make_conn(db_session, op.id, other.id, dst.id, src_ip="10.4.0.2", dst_ip="10.4.0.3")

    req = PathFinderRequest(
        src_host_id=src.id,
        dst_host_id=dst.id,
        mode="all",
        waypoints=[WaypointConstraint(host_id=hop.id, position="after", relative_to=None)],
    )
    resp = find_paths(db_session, op.id, req)
    # Only the path where hop is path[1]
    assert len(resp.paths) == 1
    assert resp.paths[0].host_ids[1] == hop.id


def test_waypoint_before_no_relative_to(db_session):
    """Waypoint position='before' with no relative_to: waypoint must be last hop before dst."""
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    hop = _make_host(db_session, op.id, "hop")
    other = _make_host(db_session, op.id, "other")
    dst = _make_host(db_session, op.id, "dst")

    # src → hop → dst
    _make_conn(db_session, op.id, src.id, hop.id, src_ip="10.5.0.0", dst_ip="10.5.0.1")
    _make_conn(db_session, op.id, hop.id, dst.id, src_ip="10.5.0.1", dst_ip="10.5.0.3")
    # src → other → dst
    _make_conn(db_session, op.id, src.id, other.id, src_ip="10.5.0.0", dst_ip="10.5.0.2")
    _make_conn(db_session, op.id, other.id, dst.id, src_ip="10.5.0.2", dst_ip="10.5.0.3")

    req = PathFinderRequest(
        src_host_id=src.id,
        dst_host_id=dst.id,
        mode="all",
        waypoints=[WaypointConstraint(host_id=hop.id, position="before", relative_to=None)],
    )
    resp = find_paths(db_session, op.id, req)
    # Only the path where hop is path[-2]
    assert len(resp.paths) == 1
    assert resp.paths[0].host_ids[-2] == hop.id


def test_waypoint_filters_all_paths(db_session):
    """Waypoint requiring an absent host → empty result."""
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    dst = _make_host(db_session, op.id, "dst")
    absent = _make_host(db_session, op.id, "absent")
    _make_conn(db_session, op.id, src.id, dst.id, src_ip="10.6.0.0", dst_ip="10.6.0.1")

    req = PathFinderRequest(
        src_host_id=src.id,
        dst_host_id=dst.id,
        mode="all",
        waypoints=[WaypointConstraint(host_id=absent.id, position="anywhere")],
    )
    resp = find_paths(db_session, op.id, req)
    assert resp.paths == []


# ─── Priority 7: Waypoint after/before with relative_to ──────────────────────

def test_waypoint_after_with_relative_to_included(db_session):
    """position='after' with relative_to=A: waypoint must appear immediately after A.

    Path: src → A → B → dst
    Waypoint: B after A → path included.
    """
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    hop_a = _make_host(db_session, op.id, "A")
    hop_b = _make_host(db_session, op.id, "B")
    dst = _make_host(db_session, op.id, "dst")

    _make_conn(db_session, op.id, src.id, hop_a.id, src_ip="10.7.0.0", dst_ip="10.7.0.1")
    _make_conn(db_session, op.id, hop_a.id, hop_b.id, src_ip="10.7.0.1", dst_ip="10.7.0.2")
    _make_conn(db_session, op.id, hop_b.id, dst.id, src_ip="10.7.0.2", dst_ip="10.7.0.3")

    req = PathFinderRequest(
        src_host_id=src.id,
        dst_host_id=dst.id,
        mode="all",
        waypoints=[WaypointConstraint(host_id=hop_b.id, position="after", relative_to=hop_a.id)],
    )
    resp = find_paths(db_session, op.id, req)
    assert len(resp.paths) == 1
    path_ids = resp.paths[0].host_ids
    assert path_ids == [src.id, hop_a.id, hop_b.id, dst.id]


def test_waypoint_after_with_relative_to_excluded(db_session):
    """position='after' with relative_to not in path → all paths excluded."""
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    hop = _make_host(db_session, op.id, "hop")
    dst = _make_host(db_session, op.id, "dst")
    absent = _make_host(db_session, op.id, "absent")  # not in any path

    _make_conn(db_session, op.id, src.id, hop.id, src_ip="10.8.0.0", dst_ip="10.8.0.1")
    _make_conn(db_session, op.id, hop.id, dst.id, src_ip="10.8.0.1", dst_ip="10.8.0.2")

    req = PathFinderRequest(
        src_host_id=src.id,
        dst_host_id=dst.id,
        mode="all",
        # hop must come after absent — but absent isn't in the path
        waypoints=[WaypointConstraint(host_id=hop.id, position="after", relative_to=absent.id)],
    )
    resp = find_paths(db_session, op.id, req)
    assert resp.paths == []


def test_waypoint_before_with_relative_to_included(db_session):
    """position='before' with relative_to=B: waypoint must appear immediately before B.

    Path: src → A → B → dst
    Waypoint: A before B → path included.
    """
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    hop_a = _make_host(db_session, op.id, "A")
    hop_b = _make_host(db_session, op.id, "B")
    dst = _make_host(db_session, op.id, "dst")

    _make_conn(db_session, op.id, src.id, hop_a.id, src_ip="10.9.0.0", dst_ip="10.9.0.1")
    _make_conn(db_session, op.id, hop_a.id, hop_b.id, src_ip="10.9.0.1", dst_ip="10.9.0.2")
    _make_conn(db_session, op.id, hop_b.id, dst.id, src_ip="10.9.0.2", dst_ip="10.9.0.3")

    req = PathFinderRequest(
        src_host_id=src.id,
        dst_host_id=dst.id,
        mode="all",
        waypoints=[WaypointConstraint(host_id=hop_a.id, position="before", relative_to=hop_b.id)],
    )
    resp = find_paths(db_session, op.id, req)
    assert len(resp.paths) == 1
    path_ids = resp.paths[0].host_ids
    assert path_ids == [src.id, hop_a.id, hop_b.id, dst.id]


def test_waypoint_before_with_relative_to_excluded(db_session):
    """position='before' with relative_to not in path → all paths excluded."""
    op = _make_op(db_session)
    src = _make_host(db_session, op.id, "src")
    hop = _make_host(db_session, op.id, "hop")
    dst = _make_host(db_session, op.id, "dst")
    absent = _make_host(db_session, op.id, "absent")

    _make_conn(db_session, op.id, src.id, hop.id, src_ip="10.10.0.0", dst_ip="10.10.0.1")
    _make_conn(db_session, op.id, hop.id, dst.id, src_ip="10.10.0.1", dst_ip="10.10.0.2")

    req = PathFinderRequest(
        src_host_id=src.id,
        dst_host_id=dst.id,
        mode="all",
        waypoints=[WaypointConstraint(host_id=hop.id, position="before", relative_to=absent.id)],
    )
    resp = find_paths(db_session, op.id, req)
    assert resp.paths == []
