"""API tests for graph endpoints."""
import pathlib

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


def test_graph_no_edge_when_fingerprint_null(client, op, host_a, host_b):
    """Credential links with no fingerprint must not produce a key_match edge.

    An unparseable key value means fingerprint=NULL. Without a fingerprint,
    the graph builder cannot confirm a key match, so edges must be empty.
    """
    cred_resp = client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "public_key", "value": "plaintext-not-a-key"},
    )
    cred = cred_resp.json()
    cred_id = cred["id"]
    # Confirm no fingerprint was computed for the invalid key material
    assert cred["fingerprint"] is None

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
    assert len(data["nodes"]) == 2
    assert data["edges"] == []


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


# ─── Priority 5: POST /ops/{op_id}/graph/paths ───────────────────────────────

def _paths_body(src_id, dst_id, mode="shortest", waypoints=None):
    body = {"src_host_id": src_id, "dst_host_id": dst_id, "mode": mode}
    if waypoints is not None:
        body["waypoints"] = waypoints
    return body


def test_paths_op_not_found(client):
    resp = client.post(
        "/api/ops/nonexistent/graph/paths",
        json=_paths_body("a", "b"),
    )
    assert resp.status_code == 404


def test_paths_no_path_between_disconnected_hosts(client, op, host_a, host_b):
    """No connections → paths list is empty, truncated is False."""
    resp = client.post(
        f"/api/ops/{op['id']}/graph/paths",
        json=_paths_body(host_a["id"], host_b["id"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["paths"] == []
    assert data["truncated"] is False


def test_paths_single_hop_connection(client, op, host_a, host_b):
    """A direct connection A→B must yield one path [A, B]."""
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
        f"/api/ops/{op['id']}/graph/paths",
        json=_paths_body(host_a["id"], host_b["id"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["paths"]) == 1
    assert data["paths"][0]["host_ids"] == [host_a["id"], host_b["id"]]
    assert data["truncated"] is False


def test_paths_key_match_edge(client, op, host_a, host_b):
    """Key-match edge (found_on_disk + authorized_key) must produce a path."""
    fixtures = pathlib.Path(__file__).parent.parent / "fixtures"
    priv = (fixtures / "id_rsa").read_bytes()
    pub = (fixtures / "id_rsa.pub").read_text().strip()

    # Upload private key to hostA
    r1 = client.post(
        f"/api/ops/{op['id']}/upload",
        data={"file_type": "private_key", "host_id": host_a["id"], "username": "alice"},
        files={"file": ("id_rsa", priv, "text/plain")},
    )
    assert r1.status_code == 200

    # Upload public key (authorized_keys) to hostB
    r2 = client.post(
        f"/api/ops/{op['id']}/upload",
        data={"file_type": "authorized_keys", "host_id": host_b["id"], "username": "root"},
        files={"file": ("authorized_keys", (pub + "\n").encode(), "text/plain")},
    )
    assert r2.status_code == 200

    # Now query paths — key match creates an edge A→B
    resp = client.post(
        f"/api/ops/{op['id']}/graph/paths",
        json=_paths_body(host_a["id"], host_b["id"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["paths"]) == 1
    path = data["paths"][0]
    assert path["host_ids"] == [host_a["id"], host_b["id"]]
    # The edge must have evidence
    assert len(path["edges"]) == 1
    assert path["edges"][0]["confidence"] == "confirmed"


# ─── Priority 12: test_graph_key_match_edge — meaningful assertion ────────────

def test_graph_key_match_edge_with_real_key(client, op, host_a, host_b):
    """Real key upload produces a confirmed key_match edge in the graph."""
    fixtures = pathlib.Path(__file__).parent.parent / "fixtures"
    priv = (fixtures / "id_rsa").read_bytes()
    pub = (fixtures / "id_rsa.pub").read_text().strip()

    client.post(
        f"/api/ops/{op['id']}/upload",
        data={"file_type": "private_key", "host_id": host_a["id"], "username": "alice"},
        files={"file": ("id_rsa", priv, "text/plain")},
    )
    client.post(
        f"/api/ops/{op['id']}/upload",
        data={"file_type": "authorized_keys", "host_id": host_b["id"], "username": "root"},
        files={"file": ("authorized_keys", (pub + "\n").encode(), "text/plain")},
    )

    resp = client.get(f"/api/ops/{op['id']}/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["edges"]) == 1
    edge = data["edges"][0]
    assert edge["src_host_id"] == host_a["id"]
    assert edge["dst_host_id"] == host_b["id"]
    assert edge["confidence"] == "confirmed"
    assert any(e["type"] == "key_match" for e in edge["evidence"])


# ─── Priority 21: _cred_label fingerprint branch (no double SHA256:) ─────────

def test_cred_label_no_double_sha256_prefix(client, op, host_a, host_b):
    """Nameless credential with fingerprint must not produce 'SHA256:SHA256:' in walkthrough.

    Uses a credential created via the API (no name set) with a fingerprint injected
    via the public key route, then a manual connection to trigger command generation.
    """
    fixtures = pathlib.Path(__file__).parent.parent / "fixtures"

    # Use the RSA pub key to create a public_key credential — no name, gets fingerprint
    # NOTE: private_key parser sets name="{filename} ({username})"; use the API directly
    # to create a nameless credential
    pub_key = (fixtures / "id_rsa.pub").read_text().strip()
    cred_pk_resp = client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "public_key", "value": pub_key},
    )
    assert cred_pk_resp.status_code == 201
    cred_pk = cred_pk_resp.json()
    cred_pk_id = cred_pk["id"]
    fingerprint = cred_pk["fingerprint"]
    assert fingerprint is not None and fingerprint.startswith("SHA256:")
    # Verify no name was set
    assert cred_pk["name"] is None

    # Create connection using the nameless fingerprinted credential
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"], "src_ip": "10.0.0.1", "src_user": "alice",
            "dst_host_id": host_b["id"], "dst_ip": "10.0.0.2", "dst_user": "root",
            "connection_type": "ssh", "direction_context": "from_dst_logs",
            "source_file": "auth.log",
            "credential_id": cred_pk_id,
        },
    )

    resp = client.post(
        f"/api/ops/{op['id']}/graph/paths/commands",
        json=_cmd_body(host_a["id"], host_b["id"]),
    )
    assert resp.status_code == 200
    p = resp.json()["paths"][0]
    # The walkthrough must not produce the double 'SHA256:SHA256:' prefix (BUG-02 fix)
    assert "SHA256:SHA256:" not in p["walkthrough"]
    # The fingerprint (with single SHA256: prefix) should appear in the walkthrough
    assert fingerprint in p["walkthrough"]


# ─── Priority 24: cross-op graph isolation ────────────────────────────────────

def test_cross_op_graph_isolation(client):
    """Credential links from op_A must not appear in op_B graph."""
    op_a = client.post("/api/ops", json={"name": "Op A"}).json()
    op_b = client.post("/api/ops", json={"name": "Op B"}).json()

    # Create hosts in op_A and link them via key match
    ha1 = client.post(f"/api/ops/{op_a['id']}/hosts", json={"nickname": "A1"}).json()
    ha2 = client.post(f"/api/ops/{op_a['id']}/hosts", json={"nickname": "A2"}).json()
    client.post(f"/api/hosts/{ha1['id']}/ips", json={"ip_address": "10.1.0.1"})
    client.post(f"/api/hosts/{ha2['id']}/ips", json={"ip_address": "10.1.0.2"})

    fixtures = pathlib.Path(__file__).parent.parent / "fixtures"
    priv = (fixtures / "id_rsa").read_bytes()
    pub = (fixtures / "id_rsa.pub").read_text().strip()

    client.post(
        f"/api/ops/{op_a['id']}/upload",
        data={"file_type": "private_key", "host_id": ha1["id"], "username": "alice"},
        files={"file": ("id_rsa", priv, "text/plain")},
    )
    client.post(
        f"/api/ops/{op_a['id']}/upload",
        data={"file_type": "authorized_keys", "host_id": ha2["id"], "username": "root"},
        files={"file": ("authorized_keys", (pub + "\n").encode(), "text/plain")},
    )

    # op_A should have an edge
    graph_a = client.get(f"/api/ops/{op_a['id']}/graph").json()
    assert len(graph_a["edges"]) == 1

    # op_B has no hosts — graph must be empty
    graph_b = client.get(f"/api/ops/{op_b['id']}/graph").json()
    assert graph_b["nodes"] == []
    assert graph_b["edges"] == []
