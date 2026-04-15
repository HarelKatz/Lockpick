"""API tests for GET /ops/{op_id}/activity endpoint."""
from datetime import datetime

import pytest


@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Test Op"})
    return resp.json()


def test_activity_op_not_found(client):
    resp = client.get("/api/ops/bad-id/activity")
    assert resp.status_code == 404


def test_activity_empty_op(client, op):
    resp = client.get(f"/api/ops/{op['id']}/activity")
    assert resp.status_code == 200
    assert resp.json() == []


def test_activity_logged_after_host_create(client, op):
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "web01"})
    resp = client.get(f"/api/ops/{op['id']}/activity")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1
    host_create_entries = [e for e in entries if e["action"] == "host.create"]
    assert len(host_create_entries) >= 1
    entry = host_create_entries[0]
    assert entry["entity_type"] == "host"


def test_activity_entries_sorted_newest_first(client, op):
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host1"})
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host2"})
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host3"})
    resp = client.get(f"/api/ops/{op['id']}/activity")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 3
    timestamps = [
        datetime.fromisoformat(e["created_at"].rstrip("Z"))
        for e in entries
    ]
    for i in range(len(timestamps) - 1):
        assert timestamps[i] >= timestamps[i + 1]


def test_activity_limit_caps_results(client, op):
    for i in range(5):
        client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": f"host{i}"})
    resp = client.get(f"/api/ops/{op['id']}/activity?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_activity_limit_too_large_returns_422(client, op):
    resp = client.get(f"/api/ops/{op['id']}/activity?limit=201")
    assert resp.status_code == 422


def test_activity_limit_zero_returns_422(client, op):
    resp = client.get(f"/api/ops/{op['id']}/activity?limit=0")
    assert resp.status_code == 422


def test_activity_default_limit(client, op):
    resp = client.get(f"/api/ops/{op['id']}/activity")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
