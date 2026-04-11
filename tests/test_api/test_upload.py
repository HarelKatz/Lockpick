"""Integration tests for the file upload endpoint."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _create_op(client) -> str:
    r = client.post("/api/ops", json={"name": "TestOp"})
    assert r.status_code == 201
    return r.json()["id"]


def _create_host(client, op_id: str, nickname: str = "web01") -> str:
    r = client.post(f"/api/ops/{op_id}/hosts", json={"nickname": nickname})
    assert r.status_code == 201
    return r.json()["id"]


def test_upload_authorized_keys(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "authorized_keys").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "authorized_keys", "host_id": host_id, "username": "alice"},
        files={"file": ("authorized_keys", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["summary"]["new_credentials"] >= 2
    assert body["file_type"] == "authorized_keys"


def test_upload_known_hosts(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "known_hosts").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "known_hosts", "host_id": host_id, "username": "bob"},
        files={"file": ("known_hosts", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["summary"]["new_connections"] >= 3


def test_upload_bash_history(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "bash_history").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "bash_history", "host_id": host_id, "username": "alice"},
        files={"file": (".bash_history", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["new_connections"] >= 5


def test_upload_passwd(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "passwd").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "passwd", "host_id": host_id},
        files={"file": ("passwd", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    # no credentials or connections from passwd
    assert body["summary"]["new_credentials"] == 0
    assert body["summary"]["new_connections"] == 0


def test_upload_auth_log(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "auth.log").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "auth_log", "host_id": host_id},
        files={"file": ("auth.log", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["new_connections"] >= 2


def test_upload_private_key(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "id_rsa").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "private_key", "host_id": host_id, "username": "alice"},
        files={"file": ("id_rsa", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["new_credentials"] == 1


def test_pivot_detection(client, tmp_path):
    """Upload a private key, then an authorized_keys with the matching public key — expect pivot message."""
    op_id = _create_op(client)
    hostA_id = _create_host(client, op_id, "hostA")
    hostB_id = _create_host(client, op_id, "hostB")

    # Upload private key to hostA
    priv_content = (FIXTURES / "id_rsa").read_bytes()
    r1 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "private_key", "host_id": hostA_id, "username": "alice"},
        files={"file": ("id_rsa", priv_content, "text/plain")},
    )
    assert r1.status_code == 200

    # Upload authorized_keys to hostB containing the matching public key
    pub_line = (FIXTURES / "id_rsa.pub").read_text().strip()
    auth_keys_content = (pub_line + "\n").encode()
    r2 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "authorized_keys", "host_id": hostB_id, "username": "root"},
        files={"file": ("authorized_keys", auth_keys_content, "text/plain")},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert len(body["pivot_opportunities"]) >= 1
    assert "hostA" in body["pivot_opportunities"][0]
    assert "hostB" in body["pivot_opportunities"][0]


def test_invalid_file_type(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "not_a_type", "host_id": host_id},
        files={"file": ("foo", b"data", "text/plain")},
    )
    assert resp.status_code == 422


def test_upload_op_not_found(client):
    resp = client.post(
        "/api/ops/nonexistent/upload",
        data={"file_type": "passwd", "host_id": "x"},
        files={"file": ("f", b"", "text/plain")},
    )
    assert resp.status_code == 404
