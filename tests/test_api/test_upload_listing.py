"""Integration tests for upload listing and serving endpoints.

GET /api/ops/{op_id}/uploads          — list_uploads
GET /api/ops/{op_id}/uploads/{name}   — get_upload
"""
import pytest
from pathlib import Path


FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Test Op"})
    assert resp.status_code == 201
    return resp.json()


# ─── list_uploads ─────────────────────────────────────────────────────────────


def test_list_uploads_op_not_found(client):
    resp = client.get("/api/ops/bad-id/uploads")
    assert resp.status_code == 404


def test_list_uploads_empty(client, op, upload_dir):
    # upload_dir exists but op subdir does not — endpoint should return []
    resp = client.get(f"/api/ops/{op['id']}/uploads")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_uploads_after_file_written(client, op, upload_dir):
    op_dir = upload_dir / op["id"]
    op_dir.mkdir()
    (op_dir / "testfile.txt").write_bytes(b"hello world")

    resp = client.get(f"/api/ops/{op['id']}/uploads")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["safe_name"] == "testfile.txt"
    assert data[0]["size_bytes"] > 0


def test_list_uploads_via_actual_upload(client, op, upload_dir):
    host_resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "upload-host"})
    assert host_resp.status_code == 201
    host_id = host_resp.json()["id"]

    fixture_path = FIXTURES / "authorized_keys"
    with open(fixture_path, "rb") as f:
        resp = client.post(
            f"/api/ops/{op['id']}/upload",
            data={"file_type": "authorized_keys", "host_id": host_id},
            files={"file": ("authorized_keys", f, "application/octet-stream")},
        )
    assert resp.status_code == 200

    list_resp = client.get(f"/api/ops/{op['id']}/uploads")
    assert list_resp.status_code == 200
    entries = list_resp.json()
    assert len(entries) == 1
    assert entries[0]["size_bytes"] > 0


def test_list_uploads_host_ids_appear(client, op, upload_dir):
    host_resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "upload-host"})
    assert host_resp.status_code == 201
    host_id = host_resp.json()["id"]

    fixture_path = FIXTURES / "authorized_keys"
    with open(fixture_path, "rb") as f:
        resp = client.post(
            f"/api/ops/{op['id']}/upload",
            data={"file_type": "authorized_keys", "host_id": host_id},
            files={"file": ("authorized_keys", f, "application/octet-stream")},
        )
    assert resp.status_code == 200

    list_resp = client.get(f"/api/ops/{op['id']}/uploads")
    assert list_resp.status_code == 200
    entries = list_resp.json()
    assert len(entries) == 1
    assert host_id in entries[0]["host_ids"]


# ─── get_upload ───────────────────────────────────────────────────────────────


def test_get_upload_op_not_found(client):
    resp = client.get("/api/ops/bad-id/uploads/somefile.txt")
    assert resp.status_code == 404


def test_get_upload_file_not_found(client, op, upload_dir):
    (upload_dir / op["id"]).mkdir()
    resp = client.get(f"/api/ops/{op['id']}/uploads/nonexistent.txt")
    assert resp.status_code == 404


def test_get_upload_path_traversal_dotdot(client, op, upload_dir):
    # "..secret" contains ".." — triggers the guard
    resp = client.get(f"/api/ops/{op['id']}/uploads/..secret")
    assert resp.status_code == 400


def test_get_upload_path_traversal_backslash(client, op, upload_dir):
    # %5C is URL-encoded backslash
    resp = client.get(f"/api/ops/{op['id']}/uploads/..%5Csecret")
    assert resp.status_code == 400


def test_get_upload_valid_file_returns_200(client, op, upload_dir):
    op_dir = upload_dir / op["id"]
    op_dir.mkdir()
    (op_dir / "testfile.txt").write_bytes(b"secret data")

    resp = client.get(f"/api/ops/{op['id']}/uploads/testfile.txt")
    assert resp.status_code == 200
    assert resp.content == b"secret data"


def test_get_upload_download_true_sets_attachment(client, op, upload_dir):
    op_dir = upload_dir / op["id"]
    op_dir.mkdir()
    (op_dir / "testfile.txt").write_bytes(b"data")

    resp = client.get(f"/api/ops/{op['id']}/uploads/testfile.txt?download=true")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("attachment")


def test_get_upload_download_false_sets_inline(client, op, upload_dir):
    op_dir = upload_dir / op["id"]
    op_dir.mkdir()
    (op_dir / "testfile.txt").write_bytes(b"data")

    resp = client.get(f"/api/ops/{op['id']}/uploads/testfile.txt?download=false")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("inline")


def test_get_upload_no_download_param_is_inline(client, op, upload_dir):
    op_dir = upload_dir / op["id"]
    op_dir.mkdir()
    (op_dir / "testfile.txt").write_bytes(b"data")

    resp = client.get(f"/api/ops/{op['id']}/uploads/testfile.txt")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("inline")
