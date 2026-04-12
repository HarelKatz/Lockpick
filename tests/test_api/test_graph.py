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


# ─── /graph/paths/commands ────────────────────────────────────────────────────

def _cmd_body(src_id, dst_id):
    return {"src_host_id": src_id, "dst_host_id": dst_id, "mode": "shortest", "waypoints": []}


def test_commands_op_not_found(client):
    resp = client.post("/api/ops/nonexistent/graph/paths/commands", json=_cmd_body("a", "b"))
    assert resp.status_code == 404


def test_commands_no_path(client, op, host_a, host_b):
    """No connections — endpoint returns empty paths list."""
    resp = client.post(
        f"/api/ops/{op['id']}/graph/paths/commands",
        json=_cmd_body(host_a["id"], host_b["id"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["paths"] == []
    assert data["truncated"] is False


def test_commands_response_shape(client, op, host_a, host_b):
    """Each path object has all four command format keys."""
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"], "src_ip": "10.0.0.1",
            "dst_host_id": host_b["id"], "dst_ip": "10.0.0.2",
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )
    resp = client.post(
        f"/api/ops/{op['id']}/graph/paths/commands",
        json=_cmd_body(host_a["id"], host_b["id"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["paths"]) == 1
    p = data["paths"][0]
    assert "proxyjump" in p
    assert "proxychains" in p
    assert "walkthrough" in p
    assert "ssh_config" in p
    assert p["host_ids"] == [host_a["id"], host_b["id"]]


def test_commands_single_hop_users(client, op, host_a, host_b):
    """Single-hop path with users — ProxyJump has no -J; users appear in output."""
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"], "src_ip": "10.0.0.1", "src_user": "bob",
            "dst_host_id": host_b["id"], "dst_ip": "10.0.0.2", "dst_user": "root",
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )
    resp = client.post(
        f"/api/ops/{op['id']}/graph/paths/commands",
        json=_cmd_body(host_a["id"], host_b["id"]),
    )
    assert resp.status_code == 200
    p = resp.json()["paths"][0]
    # ProxyJump: single hop, no -J
    assert "-J" not in p["proxyjump"]
    assert "root@10.0.0.2" in p["proxyjump"]
    # Walkthrough contains both users
    assert "bob" in p["walkthrough"]
    assert "root" in p["walkthrough"]
    # SSH config contains destination IP and user
    assert "10.0.0.2" in p["ssh_config"]
    assert "root" in p["ssh_config"]


def test_commands_single_hop_no_users(client, op, host_a, host_b):
    """Single-hop path with no users — placeholders appear in output."""
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"], "src_ip": "10.0.0.1",
            "dst_host_id": host_b["id"], "dst_ip": "10.0.0.2",
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )
    resp = client.post(
        f"/api/ops/{op['id']}/graph/paths/commands",
        json=_cmd_body(host_a["id"], host_b["id"]),
    )
    assert resp.status_code == 200
    p = resp.json()["paths"][0]
    assert "<user>" in p["proxyjump"]
    assert "<user>" in p["walkthrough"]


def test_commands_multihop(client, op, host_a, host_b):
    """Three-node path — ProxyJump uses -J; walkthrough has 2 steps; SSH config has 2 Host blocks."""
    resp_c = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "hostC"})
    host_c = resp_c.json()
    client.post(f"/api/hosts/{host_c['id']}/ips", json={"ip_address": "10.0.0.3"})

    # A→B
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"], "src_ip": "10.0.0.1", "src_user": "bob",
            "dst_host_id": host_b["id"], "dst_ip": "10.0.0.2", "dst_user": "alice",
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )
    # B→C
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_b["id"], "src_ip": "10.0.0.2", "src_user": "alice",
            "dst_host_id": host_c["id"], "dst_ip": "10.0.0.3", "dst_user": "root",
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )

    resp = client.post(
        f"/api/ops/{op['id']}/graph/paths/commands",
        json=_cmd_body(host_a["id"], host_c["id"]),
    )
    assert resp.status_code == 200
    p = resp.json()["paths"][0]
    # ProxyJump must use -J chain
    assert "-J" in p["proxyjump"]
    assert "alice@10.0.0.2" in p["proxyjump"]
    assert "root@10.0.0.3" in p["proxyjump"]
    # Walkthrough has 2 steps
    assert "Step 1:" in p["walkthrough"]
    assert "Step 2:" in p["walkthrough"]
    # SSH config has 2 Host entries (for hop B and target C)
    assert p["ssh_config"].count("Host lockpick-") == 2


def test_commands_named_credential(client, op, host_a, host_b):
    """Connection with a named credential — label appears in walkthrough."""
    cred_resp = client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "private_key", "name": "my-pivot-key", "value": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAtest"},
    )
    cred_id = cred_resp.json()["id"]

    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"], "src_ip": "10.0.0.1", "src_user": "bob",
            "dst_host_id": host_b["id"], "dst_ip": "10.0.0.2", "dst_user": "root",
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "source_file": "auth.log",
            "credential_id": cred_id,
        },
    )
    resp = client.post(
        f"/api/ops/{op['id']}/graph/paths/commands",
        json=_cmd_body(host_a["id"], host_b["id"]),
    )
    assert resp.status_code == 200
    p = resp.json()["paths"][0]
    assert "my-pivot-key" in p["walkthrough"]
