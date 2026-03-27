"""API tests for Operations endpoints."""
import pytest


def test_health_check(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_operation(client):
    resp = client.post("/api/ops", json={"name": "Test Op", "description": "A test operation"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Op"
    assert data["description"] == "A test operation"
    assert "id" in data
    assert "created_at" in data


def test_create_operation_minimal(client):
    resp = client.post("/api/ops", json={"name": "Minimal Op"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Minimal Op"
    assert data["description"] is None


def test_list_operations_empty(client):
    resp = client.get("/api/ops")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_operations(client):
    client.post("/api/ops", json={"name": "Op A"})
    client.post("/api/ops", json={"name": "Op B"})
    resp = client.get("/api/ops")
    assert resp.status_code == 200
    names = [op["name"] for op in resp.json()]
    assert "Op A" in names
    assert "Op B" in names


def test_get_operation(client):
    create_resp = client.post("/api/ops", json={"name": "Get Op"})
    op_id = create_resp.json()["id"]
    resp = client.get(f"/api/ops/{op_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == op_id


def test_get_operation_not_found(client):
    resp = client.get("/api/ops/nonexistent-id")
    assert resp.status_code == 404


def test_update_operation(client):
    create_resp = client.post("/api/ops", json={"name": "Old Name"})
    op_id = create_resp.json()["id"]
    resp = client.patch(f"/api/ops/{op_id}", json={"name": "New Name", "description": "Updated"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["description"] == "Updated"


def test_delete_operation(client):
    create_resp = client.post("/api/ops", json={"name": "To Delete"})
    op_id = create_resp.json()["id"]
    resp = client.delete(f"/api/ops/{op_id}")
    assert resp.status_code == 204
    # Confirm it's gone
    get_resp = client.get(f"/api/ops/{op_id}")
    assert get_resp.status_code == 404


def test_delete_operation_not_found(client):
    resp = client.delete("/api/ops/nonexistent-id")
    assert resp.status_code == 404
