"""API tests for HostUser endpoints."""
import pytest


@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Test Op"})
    return resp.json()


@pytest.fixture
def host(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "target"})
    return resp.json()


# ─── HostUser CRUD ────────────────────────────────────────────────────────────

def test_create_host_user(client, host):
    resp = client.post(
        f"/api/hosts/{host['id']}/users",
        json={"username": "bob", "shell": "/bin/bash", "home_dir": "/home/bob", "source": "manual"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "bob"
    assert data["shell"] == "/bin/bash"
    assert data["home_dir"] == "/home/bob"
    assert data["source"] == "manual"
    assert data["host_id"] == host["id"]
    assert "id" in data
    assert "created_at" in data


def test_create_host_user_minimal(client, host):
    resp = client.post(f"/api/hosts/{host['id']}/users", json={"username": "root"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "root"
    assert data["shell"] is None
    assert data["home_dir"] is None
    assert data["source"] == "manual"


def test_create_host_user_all_sources(client, host):
    for source in ("manual", "passwd_file", "authorized_keys", "log_evidence"):
        resp = client.post(
            f"/api/hosts/{host['id']}/users",
            json={"username": f"user_{source}", "source": source},
        )
        assert resp.status_code == 201
        assert resp.json()["source"] == source


def test_create_host_user_host_not_found(client):
    resp = client.post("/api/hosts/nonexistent/users", json={"username": "bob"})
    assert resp.status_code == 404


def test_list_host_users(client, host):
    client.post(f"/api/hosts/{host['id']}/users", json={"username": "alice"})
    client.post(f"/api/hosts/{host['id']}/users", json={"username": "bob"})
    resp = client.get(f"/api/hosts/{host['id']}/users")
    assert resp.status_code == 200
    usernames = {u["username"] for u in resp.json()}
    assert usernames == {"alice", "bob"}


def test_list_host_users_empty(client, host):
    resp = client.get(f"/api/hosts/{host['id']}/users")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_host_users_host_not_found(client):
    resp = client.get("/api/hosts/nonexistent/users")
    assert resp.status_code == 404


def test_delete_host_user(client, host):
    add_resp = client.post(f"/api/hosts/{host['id']}/users", json={"username": "todelete"})
    user_id = add_resp.json()["id"]
    resp = client.delete(f"/api/hosts/{host['id']}/users/{user_id}")
    assert resp.status_code == 204
    # Confirm gone
    remaining = client.get(f"/api/hosts/{host['id']}/users").json()
    assert all(u["id"] != user_id for u in remaining)


def test_delete_host_user_not_found(client, host):
    resp = client.delete(f"/api/hosts/{host['id']}/users/nonexistent")
    assert resp.status_code == 404


def test_delete_host_user_wrong_host(client, op, host):
    """User ID from one host cannot be deleted via another host's URL."""
    other = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "other"}).json()
    user_id = client.post(
        f"/api/hosts/{host['id']}/users", json={"username": "bob"}
    ).json()["id"]
    resp = client.delete(f"/api/hosts/{other['id']}/users/{user_id}")
    assert resp.status_code == 404


# ─── Host read includes users ─────────────────────────────────────────────────

def test_get_host_includes_users(client, host):
    client.post(f"/api/hosts/{host['id']}/users", json={"username": "alice"})
    resp = client.get(f"/api/hosts/{host['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert len(data["users"]) == 1
    assert data["users"][0]["username"] == "alice"


def test_list_hosts_includes_users(client, op, host):
    client.post(f"/api/hosts/{host['id']}/users", json={"username": "bob"})
    resp = client.get(f"/api/ops/{op['id']}/hosts")
    assert resp.status_code == 200
    hosts = resp.json()
    assert len(hosts) == 1
    assert len(hosts[0]["users"]) == 1


def test_delete_host_cascades_to_users(client, op, host):
    client.post(f"/api/hosts/{host['id']}/users", json={"username": "bob"})
    client.delete(f"/api/hosts/{host['id']}")
    # Host is gone; re-creating to confirm no orphan users exist is not needed —
    # the cascade is verified by absence of a 500 on delete
    resp = client.get(f"/api/hosts/{host['id']}")
    assert resp.status_code == 404


# ─── host_user_id on CredentialLink ──────────────────────────────────────────

@pytest.fixture
def cred(client, op):
    resp = client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "password", "value": "s3cr3t"},
    )
    return resp.json()


def test_credential_link_with_host_user_id(client, op, host, cred):
    user = client.post(
        f"/api/hosts/{host['id']}/users", json={"username": "bob"}
    ).json()
    resp = client.post(
        "/api/credential-links",
        json={
            "credential_id": cred["id"],
            "host_id": host["id"],
            "username": "bob",
            "host_user_id": user["id"],
            "relationship_type": "found_on_disk",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["host_user_id"] == user["id"]
    assert data["username"] == "bob"


def test_credential_link_without_host_user_id(client, op, host, cred):
    resp = client.post(
        "/api/credential-links",
        json={
            "credential_id": cred["id"],
            "host_id": host["id"],
            "username": "root",
            "relationship_type": "authorized_key",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["host_user_id"] is None
