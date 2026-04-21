"""Tests for HostNote CRUD endpoints."""
import pytest


@pytest.fixture
def op(client):
    """Create a test operation."""
    resp = client.post("/api/ops", json={"name": "Test Op"})
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def host(client, op):
    """Create a test host in the operation."""
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "web01"})
    assert resp.status_code == 201
    return resp.json()


def test_create_note(client, op, host):
    resp = client.post(f"/api/hosts/{host['id']}/notes", json={"content": "First note"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "First note"
    assert data["host_id"] == host["id"]
    assert data["op_id"] == op["id"]
    assert "id" in data
    assert "created_at" in data


def test_list_notes(client, op, host):
    client.post(f"/api/hosts/{host['id']}/notes", json={"content": "Note A"})
    client.post(f"/api/hosts/{host['id']}/notes", json={"content": "Note B"})
    resp = client.get(f"/api/hosts/{host['id']}/notes")
    assert resp.status_code == 200
    notes = resp.json()
    assert len(notes) == 2
    contents = [n["content"] for n in notes]
    assert "Note A" in contents
    assert "Note B" in contents


def test_delete_note(client, op, host):
    create_resp = client.post(f"/api/hosts/{host['id']}/notes", json={"content": "To delete"})
    note_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/hosts/{host['id']}/notes/{note_id}")
    assert del_resp.status_code == 204

    list_resp = client.get(f"/api/hosts/{host['id']}/notes")
    assert list_resp.json() == []


def test_note_404_on_invalid_host(client, op):
    resp = client.post("/api/hosts/nonexistent-host-id/notes", json={"content": "Orphan note"})
    assert resp.status_code == 404


def test_delete_note_404_on_wrong_host(client, op, host):
    """Deleting a note with a mismatched host returns 404."""
    # Create a second host
    other = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "other"}).json()
    note_id = client.post(f"/api/hosts/{host['id']}/notes", json={"content": "test"}).json()["id"]

    # Try to delete using the other host's path
    resp = client.delete(f"/api/hosts/{other['id']}/notes/{note_id}")
    assert resp.status_code == 404


def test_notes_returned_in_host_read(client, op, host):
    """HostRead now includes notes list."""
    client.post(f"/api/hosts/{host['id']}/notes", json={"content": "Inline note"})
    resp = client.get(f"/api/hosts/{host['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert "notes" in data
    assert len(data["notes"]) == 1
    assert data["notes"][0]["content"] == "Inline note"
