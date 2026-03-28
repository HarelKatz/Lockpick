"""API tests for Credentials, CredentialLinks endpoints."""
import pytest

# A minimal valid Ed25519 private key for testing key inference.
# This is a throwaway test key — not used anywhere real.
TEST_ED25519_KEY = """\
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBY2fKCgfqWFBfDLHXmFnPZolRnb7Hv3u3HBkSx8vgxcAAAAJhkRqWEZE
alhAAAAAtzc2gtZWQyNTUxOQAAACBY2fKCgfqWFBfDLHXmFnPZolRnb7Hv3u3HBkSx8v
gxcAAAAEGtest+examplekeyforlocpicktest+AAAAAAAAAAAAAAAAAAAthZW EXAMPLE==
-----END OPENSSH PRIVATE KEY-----
"""


@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Test Op"})
    return resp.json()


@pytest.fixture
def host(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "target"})
    return resp.json()


@pytest.fixture
def password_cred(client, op):
    resp = client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "password", "value": "s3cr3t", "comment": "admin pass"},
    )
    return resp.json()


# ─── Credential CRUD ──────────────────────────────────────────────────────────

def test_create_password_credential(client, op):
    resp = client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "password", "value": "hunter2"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["cred_type"] == "password"
    assert data["value"] == "hunter2"
    assert data["fingerprint"] is None
    assert data["key_type"] is None


def test_create_credential_op_not_found(client):
    resp = client.post(
        "/api/ops/bad-id/credentials",
        json={"cred_type": "password", "value": "x"},
    )
    assert resp.status_code == 404


def test_list_credentials(client, op):
    client.post(f"/api/ops/{op['id']}/credentials", json={"cred_type": "password", "value": "a"})
    client.post(f"/api/ops/{op['id']}/credentials", json={"cred_type": "password", "value": "b"})
    resp = client.get(f"/api/ops/{op['id']}/credentials")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_credential(client, op, password_cred):
    resp = client.get(f"/api/credentials/{password_cred['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == password_cred["id"]


def test_get_credential_not_found(client):
    resp = client.get("/api/credentials/nonexistent")
    assert resp.status_code == 404


def test_update_credential_comment(client, op, password_cred):
    resp = client.patch(
        f"/api/credentials/{password_cred['id']}",
        json={"comment": "updated comment"},
    )
    assert resp.status_code == 200
    assert resp.json()["comment"] == "updated comment"


def test_update_credential_value(client, op, password_cred):
    resp = client.patch(
        f"/api/credentials/{password_cred['id']}",
        json={"value": "newpassword"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["value"] == "newpassword"
    # Password creds don't get fingerprint inferred
    assert data["fingerprint"] is None


def test_update_credential_not_found(client):
    resp = client.patch("/api/credentials/bad-id", json={"comment": "x"})
    assert resp.status_code == 404


def test_delete_credential(client, op, password_cred):
    resp = client.delete(f"/api/credentials/{password_cred['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/credentials/{password_cred['id']}").status_code == 404


# ─── CredentialLink CRUD ──────────────────────────────────────────────────────

@pytest.fixture
def cred_link(client, op, host, password_cred):
    resp = client.post(
        "/api/credential-links",
        json={
            "credential_id": password_cred["id"],
            "host_id": host["id"],
            "username": "root",
            "relationship_type": "accepted_password",
        },
    )
    return resp.json()


def test_create_credential_link(client, op, host, password_cred):
    resp = client.post(
        "/api/credential-links",
        json={
            "credential_id": password_cred["id"],
            "host_id": host["id"],
            "username": "bob",
            "relationship_type": "found_on_disk",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "bob"
    assert data["relationship_type"] == "found_on_disk"


def test_create_credential_link_missing_cred(client, host):
    resp = client.post(
        "/api/credential-links",
        json={
            "credential_id": "nonexistent",
            "host_id": host["id"],
            "relationship_type": "found_on_disk",
        },
    )
    assert resp.status_code == 404


def test_create_credential_link_missing_host(client, op, password_cred):
    resp = client.post(
        "/api/credential-links",
        json={
            "credential_id": password_cred["id"],
            "host_id": "nonexistent",
            "relationship_type": "found_on_disk",
        },
    )
    assert resp.status_code == 404


def test_list_credential_links(client, op, cred_link):
    resp = client.get(f"/api/ops/{op['id']}/credential-links")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_update_credential_link_username(client, cred_link):
    resp = client.patch(
        f"/api/credential-links/{cred_link['id']}",
        json={"username": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_update_credential_link_relationship(client, cred_link):
    resp = client.patch(
        f"/api/credential-links/{cred_link['id']}",
        json={"relationship_type": "used_in_connection"},
    )
    assert resp.status_code == 200
    assert resp.json()["relationship_type"] == "used_in_connection"


def test_update_credential_link_file_source(client, cred_link):
    resp = client.patch(
        f"/api/credential-links/{cred_link['id']}",
        json={"file_source": "/home/bob/.ssh/id_rsa"},
    )
    assert resp.status_code == 200
    assert resp.json()["file_source"] == "/home/bob/.ssh/id_rsa"


def test_update_credential_link_not_found(client):
    resp = client.patch("/api/credential-links/bad-id", json={"username": "x"})
    assert resp.status_code == 404


def test_delete_credential_link(client, op, cred_link):
    resp = client.delete(f"/api/credential-links/{cred_link['id']}")
    assert resp.status_code == 204
    links = client.get(f"/api/ops/{op['id']}/credential-links").json()
    assert len(links) == 0
