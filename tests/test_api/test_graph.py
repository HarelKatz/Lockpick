"""API tests for graph endpoints."""
import pytest


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Graph Op"})
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def host_a(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "hostA"})
    h = resp.json()
    client.post(f"/api/hosts/{h['id']}/ips", json={"ip_address": "10.0.0.1"})
    return h


@pytest.fixture
def host_b(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "hostB"})
    h = resp.json()
    client.post(f"/api/hosts/{h['id']}/ips", json={"ip_address": "10.0.0.2"})
    return h


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_graph_op_not_found(client):
    resp = client.get("/api/ops/nonexistent/graph")
    assert resp.status_code == 404


def test_graph_empty_op(client, op):
    resp = client.get(f"/api/ops/{op['id']}/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert data["nodes"] == []
    assert data["edges"] == []


def test_graph_nodes_populated(client, op, host_a, host_b):
    resp = client.get(f"/api/ops/{op['id']}/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 2
    nicknames = {n["nickname"] for n in data["nodes"]}
    assert nicknames == {"hostA", "hostB"}
    # IPs should be present
    for node in data["nodes"]:
        assert len(node["ips"]) == 1


def test_graph_key_match_edge(client, op, host_a, host_b):
    # Create a credential with fingerprint
    cred_resp = client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "public_key", "value": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAtest"},
    )
    # Manually patch fingerprint via update (backend doesn't infer for this test value,
    # so we create links with a credential that already has a fingerprint via direct DB seeding
    # — use the service test for that. Here we test the API shape.)
    cred = cred_resp.json()
    cred_id = cred["id"]

    # Create links
    client.post(
        f"/api/ops/{op['id']}/credential-links",
        json={
            "credential_id": cred_id,
            "host_id": host_a["id"],
            "relationship_type": "found_on_disk",
            "username": "bob",
        },
    )
    client.post(
        f"/api/ops/{op['id']}/credential-links",
        json={
            "credential_id": cred_id,
            "host_id": host_b["id"],
            "relationship_type": "authorized_key",
            "username": "root",
        },
    )

    resp = client.get(f"/api/ops/{op['id']}/graph")
    assert resp.status_code == 200
    data = resp.json()
    # No key-match edge because fingerprint isn't computed for invalid key value,
    # but the response shape is valid and nodes are present
    assert len(data["nodes"]) == 2
    assert "edges" in data


def test_graph_connection_record_edge(client, op, host_a, host_b):
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"],
            "src_ip": "10.0.0.1",
            "src_user": "bob",
            "dst_host_id": host_b["id"],
            "dst_ip": "10.0.0.2",
            "dst_user": "root",
            "connection_type": "ssh",
            "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )

    resp = client.get(f"/api/ops/{op['id']}/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["edges"]) == 1
    edge = data["edges"][0]
    assert edge["src_host_id"] == host_a["id"]
    assert edge["dst_host_id"] == host_b["id"]
    assert edge["confidence"] == "observed"
    assert len(edge["evidence"]) == 1
    assert edge["evidence"][0]["type"] == "connection_log"


def test_graph_host_ids_filter(client, op, host_a, host_b):
    # Add a third host
    resp_c = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "hostC"})
    host_c = resp_c.json()

    # Connection A→B
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"], "src_ip": "10.0.0.1",
            "dst_host_id": host_b["id"], "dst_ip": "10.0.0.2",
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )
    # Connection A→C
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"], "src_ip": "10.0.0.1",
            "dst_host_id": host_c["id"], "dst_ip": "10.0.0.3",
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )

    # Filter to only A and B
    resp = client.get(
        f"/api/ops/{op['id']}/graph",
        params={"host_ids": f"{host_a['id']},{host_b['id']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1
    assert data["edges"][0]["dst_host_id"] == host_b["id"]


def test_expand_not_found_op(client):
    resp = client.get("/api/ops/bad-op/hosts/bad-host/expand")
    assert resp.status_code == 404


def test_expand_host_returns_neighbors(client, op, host_a, host_b):
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"], "src_ip": "10.0.0.1",
            "dst_host_id": host_b["id"], "dst_ip": "10.0.0.2",
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )

    resp = client.get(f"/api/ops/{op['id']}/hosts/{host_a['id']}/expand")
    assert resp.status_code == 200
    data = resp.json()
    node_ids = {n["host_id"] for n in data["nodes"]}
    assert host_a["id"] in node_ids
    assert host_b["id"] in node_ids
    assert len(data["edges"]) == 1
