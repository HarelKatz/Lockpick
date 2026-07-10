"""Unit tests for the OpBuilder REST driver (tests/opbuilder/rest.py).

Exercises the builder against the pytest ``TestClient`` fixture. The httpx.Client
path is covered end-to-end by ``make test-e2e`` (seed_e2e.py drives the same
builder over a live server).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.opbuilder import LoadedOp, OpBuilder

NET = Path(__file__).resolve().parent.parent / "fixtures" / "network"
NET_TOPOLOGY = NET / "topology.json"


def test_op_creates_operation_and_returns_id(client):
    b = OpBuilder(client)
    op_id = b.op("MyOp")
    assert isinstance(op_id, str) and op_id
    r = client.get(f"/api/ops/{op_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "MyOp"


def test_host_and_ip_creation(client):
    b = OpBuilder(client)
    op_id = b.op("H")
    hid = b.host(op_id, "alpha")
    assert isinstance(hid, str) and hid
    b.ip(hid, "10.0.0.5")
    ips = client.get(f"/api/hosts/{hid}/ips").json()
    assert [i["ip_address"] for i in ips] == ["10.0.0.5"]


def test_connection_produces_graph_edge(client):
    b = OpBuilder(client)
    op_id = b.op("C")
    a = b.host(op_id, "a")
    b.ip(a, "10.0.0.1")
    z = b.host(op_id, "z")
    b.ip(z, "10.0.0.2")
    b.connection(
        op_id,
        src_host_id=a,
        src_ip="10.0.0.1",
        src_user="u",
        dst_host_id=z,
        dst_ip="10.0.0.2",
        dst_user="v",
        connection_type="ssh",
        direction_context="from_dst_logs",
        auth_method="password",
        source_file="t",
    )
    graph = b.graph(op_id)
    pairs = {(e["src_host_id"], e["dst_host_id"]) for e in graph["edges"]}
    assert (a, z) in pairs


def test_credential_and_link_produce_key_match_edge(client):
    """A public-key credential linked found_on_disk→authorized_key yields a confirmed key_match edge."""
    b = OpBuilder(client)
    op_id = b.op("K")
    src = b.host(op_id, "src")
    dst = b.host(op_id, "dst")
    cid = b.credential(op_id, cred_type="public_key", value="ssh-ed25519 QUJDMTIz kp", name="kp")
    b.credential_link(credential_id=cid, host_id=src, relationship_type="found_on_disk", username="root")
    b.credential_link(credential_id=cid, host_id=dst, relationship_type="authorized_key", username="root")
    graph = b.graph(op_id)
    edges_by_pair = {(e["src_host_id"], e["dst_host_id"]): e for e in graph["edges"]}
    edge = edges_by_pair.get((src, dst))
    assert edge is not None
    assert any(ev["type"] == "key_match" for ev in edge["evidence"])
    assert edge["confidence"] == "confirmed"


def test_apply_topology_returns_loaded_op(client):
    topo = {
        "hosts": [
            {"nickname": "a", "ip": "10.0.0.1", "files": []},
            {"nickname": "b", "ip": "10.0.0.2", "files": []},
        ],
        "connections": [
            {
                "src": "a",
                "dst": "b",
                "src_user": "x",
                "dst_user": "y",
                "timestamp": None,
                "connection_type": "ssh",
                "direction_context": "from_dst_logs",
                "auth_method": "password",
                "source_file": "t",
            },
        ],
    }
    lo = OpBuilder(client).apply_topology(topo)

    # dataclass access
    assert isinstance(lo, LoadedOp)
    assert isinstance(lo.op_id, str) and lo.op_id
    assert set(lo.host_ids) == {"a", "b"}
    assert lo.topology is topo

    # dict-style access — the shape the migrated fixtures rely on
    assert lo["op_id"] == lo.op_id
    assert lo["host_ids"] == lo.host_ids
    assert lo["topology"] is topo
    assert lo["graph"] == lo.graph

    node_nicks = {n["nickname"] for n in lo["graph"]["nodes"]}
    assert node_nicks == {"a", "b"}
    pairs = {(e["src_host_id"], e["dst_host_id"]) for e in lo["graph"]["edges"]}
    assert (lo.host_ids["a"], lo.host_ids["b"]) in pairs


def test_apply_topology_empty_hosts(client):
    lo = OpBuilder(client).apply_topology({"hosts": []})
    assert lo.host_ids == {}
    assert lo["graph"]["nodes"] == []


def test_apply_topology_uploads_files(tmp_path, client):
    """Files declared on a host are uploaded; fixtures_root resolves relative paths."""
    key = tmp_path / "id_rsa.pub"
    key.write_text("ssh-ed25519 QUJDeHl6 alice")
    topo = {
        "hosts": [
            {
                "nickname": "h1",
                "ip": "10.1.0.1",
                "files": [{"path": "id_rsa.pub", "file_type": "public_key", "username": "alice"}],
            },
        ],
    }
    lo = OpBuilder(client).apply_topology(topo, fixtures_root=tmp_path)
    assert {n["nickname"] for n in lo["graph"]["nodes"]} == {"h1"}
    creds = client.get(f"/api/ops/{lo.op_id}/credentials").json()
    assert len(creds) == 1


@pytest.mark.skipif(not NET_TOPOLOGY.exists(), reason="network fixtures not generated")
def test_apply_topology_reproduces_network_scenario(client):
    """Loading the real network topology.json reproduces the scenario graph.

    This is the drop-in-faithfulness proof for the scenario fixture migration:
    same node count, same 6 key-match edges, same isolated 'monitoring' host.
    """
    topology = json.loads(NET_TOPOLOGY.read_text())
    lo = OpBuilder(client).apply_topology(topology, fixtures_root=NET)

    node_nicks = {n["nickname"] for n in lo["graph"]["nodes"]}
    assert node_nicks == {h["nickname"] for h in topology["hosts"]}

    key_match_edges = [
        e for e in lo["graph"]["edges"]
        if any(ev["type"] == "key_match" for ev in e["evidence"])
    ]
    assert len(key_match_edges) == 6

    monitoring_id = lo.host_ids["monitoring"]
    connected = [
        e for e in lo["graph"]["edges"]
        if monitoring_id in (e["src_host_id"], e["dst_host_id"])
    ]
    assert connected == []
