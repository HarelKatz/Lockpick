"""API tests for the global search endpoint."""
import pytest


@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Test Op"})
    return resp.json()


# ─── Query validation ─────────────────────────────────────────────────────────

def test_search_query_too_short_returns_422(client, op):
    resp = client.get(f"/api/ops/{op['id']}/search?q=x")
    assert resp.status_code == 422


def test_search_op_not_found(client):
    resp = client.get("/api/ops/bad-op-id/search?q=foo")
    assert resp.status_code == 404


# ─── Empty results ────────────────────────────────────────────────────────────

def test_search_no_matches_returns_empty(client, op):
    resp = client.get(f"/api/ops/{op['id']}/search?q=foo")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"query": "foo", "results": [], "total": 0}


def test_search_echoes_query_and_total(client, op):
    resp = client.get(f"/api/ops/{op['id']}/search?q=nothing")
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "nothing"
    assert data["total"] == len(data["results"])


# ─── Host matching ────────────────────────────────────────────────────────────

def test_search_matches_host_by_nickname(client, op):
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "webserver01"})
    resp = client.get(f"/api/ops/{op['id']}/search?q=webserver")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    match = next(r for r in data["results"] if r["type"] == "host")
    assert match["matched_field"] == "nickname"
    assert "webserver" in match["snippet"]


def test_search_matches_host_by_comment(client, op):
    client.post(
        f"/api/ops/{op['id']}/hosts",
        json={"nickname": "box01", "comment": "dev box"},
    )
    resp = client.get(f"/api/ops/{op['id']}/search?q=dev")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    match = next(r for r in data["results"] if r["type"] == "host")
    assert match["matched_field"] == "comment"


# ─── Credential matching ──────────────────────────────────────────────────────

def test_search_matches_credential_by_name(client, op):
    client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "password", "value": "x", "name": "alice_key"},
    )
    resp = client.get(f"/api/ops/{op['id']}/search?q=alice")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    match = next(r for r in data["results"] if r["type"] == "credential")
    assert match["matched_field"] == "name"


# fingerprint is backend-computed (not user-supplied), so we skip the
# fingerprint-search test — there is no reliable way to supply a known
# fingerprint via the create payload.


# ─── Host IP matching ─────────────────────────────────────────────────────────

def test_search_matches_host_ip(client, op):
    host_resp = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "iphost"}
    )
    host_id = host_resp.json()["id"]
    client.post(f"/api/hosts/{host_id}/ips", json={"ip_address": "10.0.1.50"})

    resp = client.get(f"/api/ops/{op['id']}/search?q=10.0.1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    match = next(r for r in data["results"] if r["type"] == "host_ip")
    assert match["matched_field"] == "ip_address"
    assert "10.0.1" in match["snippet"]


# ─── Connection matching ──────────────────────────────────────────────────────

def test_search_matches_connection_by_src_ip(client, op):
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_ip": "192.168.5.5",
            "dst_ip": "10.0.0.1",
            "direction_context": "from_src_logs",
            "source_file": "bash_history",
        },
    )
    resp = client.get(f"/api/ops/{op['id']}/search?q=192.168.5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    match = next(r for r in data["results"] if r["type"] == "connection")
    assert match["matched_field"] == "src_ip"


def test_search_matches_connection_by_src_user(client, op):
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.0.2",
            "src_user": "jsmith",
            "direction_context": "from_src_logs",
            "source_file": "bash_history",
        },
    )
    resp = client.get(f"/api/ops/{op['id']}/search?q=jsmith")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    match = next(r for r in data["results"] if r["type"] == "connection")
    assert match["matched_field"] == "src_user"


def test_search_matches_connection_by_raw_line(client, op):
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.0.2",
            "direction_context": "from_dst_logs",
            "source_file": "auth.log",
            "raw_line": "Accepted publickey for root",
        },
    )
    resp = client.get(f"/api/ops/{op['id']}/search?q=Accepted")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    match = next(r for r in data["results"] if r["type"] == "connection")
    assert match["matched_field"] == "raw_line"


# ─── Host User matching ───────────────────────────────────────────────────────

def test_search_matches_host_user_by_username(client, op):
    host_resp = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "userhost"}
    )
    host_id = host_resp.json()["id"]
    client.post(f"/api/hosts/{host_id}/users", json={"username": "deployer"})

    resp = client.get(f"/api/ops/{op['id']}/search?q=deploy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    match = next(r for r in data["results"] if r["type"] == "host_user")
    assert match["matched_field"] == "username"
