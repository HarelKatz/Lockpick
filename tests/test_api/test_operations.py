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


def test_create_operation_with_summary_and_briefing(client):
    resp = client.post("/api/ops", json={
        "name": "Briefed Op",
        "summary": "Internal net, 3 footholds.",
        "briefing": "## Scope\n\n- 10.0.0.0/24 in scope\n- No DoS",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["summary"] == "Internal net, 3 footholds."
    assert data["briefing"] == "## Scope\n\n- 10.0.0.0/24 in scope\n- No DoS"


def test_create_operation_summary_and_briefing_default_to_none(client):
    resp = client.post("/api/ops", json={"name": "Bare Op"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["summary"] is None
    assert data["briefing"] is None


def test_update_operation_summary_and_briefing(client):
    op_id = client.post("/api/ops", json={"name": "Op"}).json()["id"]
    resp = client.patch(f"/api/ops/{op_id}", json={
        "summary": "Now 5 hosts owned.",
        "briefing": "Long form notes.",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "Now 5 hosts owned."
    assert data["briefing"] == "Long form notes."
    assert data["name"] == "Op"


def test_update_operation_omitting_summary_leaves_it_intact(client):
    """A PATCH that only renames must not wipe the briefing fields."""
    op_id = client.post("/api/ops", json={
        "name": "Op", "summary": "keep me", "briefing": "keep me too",
    }).json()["id"]
    resp = client.patch(f"/api/ops/{op_id}", json={"name": "Renamed"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Renamed"
    assert data["summary"] == "keep me"
    assert data["briefing"] == "keep me too"


def test_update_operation_can_clear_summary_with_empty_string(client):
    op_id = client.post("/api/ops", json={"name": "Op", "summary": "temporary"}).json()["id"]
    resp = client.patch(f"/api/ops/{op_id}", json={"summary": ""})
    assert resp.status_code == 200
    assert resp.json()["summary"] == ""


@pytest.mark.parametrize("field", ["description", "summary", "briefing"])
def test_update_operation_can_clear_optional_field_with_null(client, field):
    """An explicit null clears the field — that is what the edit modal sends."""
    op_id = client.post("/api/ops", json={"name": "Op", field: "temporary"}).json()["id"]
    resp = client.patch(f"/api/ops/{op_id}", json={field: None})
    assert resp.status_code == 200
    assert resp.json()[field] is None


def test_update_operation_null_name_is_ignored(client):
    """name is NOT NULL — an explicit null must not blank it."""
    op_id = client.post("/api/ops", json={"name": "Keep Me"}).json()["id"]
    resp = client.patch(f"/api/ops/{op_id}", json={"name": None})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Keep Me"


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
