"""API tests for GET /ops/{op_id}/stats endpoint."""
import pytest


@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Test Op"})
    return resp.json()


def test_stats_op_not_found(client):
    resp = client.get("/api/ops/bad-id/stats")
    assert resp.status_code == 404


def test_stats_empty_op_all_zeroes(client, op):
    resp = client.get(f"/api/ops/{op['id']}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["host_count"] == 0
    assert data["credential_count"] == 0
    assert data["connection_count"] == 0
    assert data["total_records"] == 0
    assert data["latest_activity_at"] is None


def test_stats_host_count_increments(client, op):
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host1"})
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host2"})
    resp = client.get(f"/api/ops/{op['id']}/stats")
    assert resp.status_code == 200
    assert resp.json()["host_count"] == 2


def test_stats_credential_count_increments(client, op):
    client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "password", "value": "secret"},
    )
    resp = client.get(f"/api/ops/{op['id']}/stats")
    assert resp.status_code == 200
    assert resp.json()["credential_count"] == 1


def test_stats_connection_count_increments(client, op):
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.0.2",
            "connection_type": "ssh",
            "direction_context": "from_src_logs",
            "source_file": "manual",
        },
    )
    resp = client.get(f"/api/ops/{op['id']}/stats")
    assert resp.status_code == 200
    assert resp.json()["connection_count"] == 1


def test_stats_total_records_is_sum(client, op):
    # Add 2 hosts, 1 credential, 1 connection
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host1"})
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host2"})
    client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "password", "value": "secret"},
    )
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.0.2",
            "direction_context": "from_src_logs",
            "source_file": "manual",
        },
    )
    resp = client.get(f"/api/ops/{op['id']}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_records"] == data["host_count"] + data["credential_count"] + data["connection_count"]
    assert data["total_records"] == 4


def test_stats_latest_activity_at_not_null(client, op):
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host1"})
    resp = client.get(f"/api/ops/{op['id']}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["latest_activity_at"] is not None
    assert isinstance(data["latest_activity_at"], str)
    # Verify it parses as an ISO datetime
    from datetime import datetime
    datetime.fromisoformat(data["latest_activity_at"].rstrip("Z"))
