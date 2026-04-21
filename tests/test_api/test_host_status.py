"""API tests for host status tag feature."""
import pytest


@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Test Op"})
    return resp.json()


@pytest.fixture
def host(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "target"})
    return resp.json()


def test_set_status(client, op, host):
    resp = client.patch(f"/api/hosts/{host['id']}", json={"status": "compromised"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "compromised"

    get_resp = client.get(f"/api/hosts/{host['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "compromised"


def test_clear_status(client, op, host):
    # Set a status first
    client.patch(f"/api/hosts/{host['id']}", json={"status": "pivot"})
    assert client.get(f"/api/hosts/{host['id']}").json()["status"] == "pivot"

    # Clear it by sending null
    resp = client.patch(f"/api/hosts/{host['id']}", json={"status": None})
    assert resp.status_code == 200
    assert resp.json()["status"] is None


def test_status_defaults_to_null(client, op, host):
    resp = client.get(f"/api/hosts/{host['id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] is None


def test_omitting_status_does_not_clear_it(client, op, host):
    """PATCH with no 'status' key must not change an existing status."""
    client.patch(f"/api/hosts/{host['id']}", json={"status": "target"})
    assert client.get(f"/api/hosts/{host['id']}").json()["status"] == "target"

    # PATCH only nickname — status must remain unchanged
    resp = client.patch(f"/api/hosts/{host['id']}", json={"nickname": "renamed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "target"


def test_status_in_graph_response(client, op, host):
    client.patch(f"/api/hosts/{host['id']}", json={"status": "compromised"})
    resp = client.get(f"/api/ops/{op['id']}/graph")
    assert resp.status_code == 200
    nodes = resp.json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["status"] == "compromised"


def test_invalid_status_rejected(client, op, host):
    resp = client.patch(f"/api/hosts/{host['id']}", json={"status": "invalid_value"})
    # Pydantic validates the Literal type and returns 422 Unprocessable Entity
    assert resp.status_code == 422


def test_all_status_values_accepted(client, op, host):
    valid_statuses = ["entry_point", "compromised", "pivot", "target", "scoped_out", "unreachable"]
    for status in valid_statuses:
        resp = client.patch(f"/api/hosts/{host['id']}", json={"status": status})
        assert resp.status_code == 200, f"Expected 200 for status={status}, got {resp.status_code}"
        assert resp.json()["status"] == status
