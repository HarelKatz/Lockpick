"""API tests for ConnectionRecord endpoints."""
import pytest


@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Test Op"})
    return resp.json()


@pytest.fixture
def host_a(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "hostA"})
    h = resp.json()
    client.post(f"/api/hosts/{h['id']}/ips", json={"ip_address": "10.0.0.1"})
    return h


@pytest.fixture
def host_b(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "hostB"})
    h = resp.json()
    client.post(f"/api/hosts/{h['id']}/ips", json={"ip_address": "10.0.0.2"})
    return h


@pytest.fixture
def conn(client, op, host_a, host_b):
    resp = client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_host_id": host_a["id"],
            "src_ip": "10.0.0.1",
            "src_user": "bob",
            "dst_host_id": host_b["id"],
            "dst_ip": "10.0.0.2",
            "dst_user": "root",
            "connection_type": "ssh",
            "direction_context": "from_src_logs",
            "source_file": "manual",
        },
    )
    return resp.json()


# ─── ConnectionRecord CRUD ────────────────────────────────────────────────────

def test_create_connection(client, op, host_a, host_b):
    resp = client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.0.2",
            "connection_type": "ssh",
            "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["src_ip"] == "10.0.0.1"
    assert data["dst_ip"] == "10.0.0.2"
    assert data["connection_type"] == "ssh"
    assert data["direction_context"] == "from_dst_logs"
    assert data["op_id"] == op["id"]


def test_create_connection_op_not_found(client):
    resp = client.post(
        "/api/ops/bad-id/connections",
        json={"src_ip": "1.1.1.1", "dst_ip": "2.2.2.2", "direction_context": "from_src_logs", "source_file": "x"},
    )
    assert resp.status_code == 404


def test_list_connections(client, op, conn):
    resp = client.get(f"/api/ops/{op['id']}/connections")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_connections_filter_src(client, op, host_a, host_b, conn):
    resp = client.get(f"/api/ops/{op['id']}/connections?src_host_id={host_a['id']}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp2 = client.get(f"/api/ops/{op['id']}/connections?src_host_id={host_b['id']}")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 0


def test_list_connections_filter_dst(client, op, host_a, host_b, conn):
    resp = client.get(f"/api/ops/{op['id']}/connections?dst_host_id={host_b['id']}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_connection(client, conn):
    resp = client.get(f"/api/connections/{conn['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == conn["id"]


def test_get_connection_not_found(client):
    resp = client.get("/api/connections/nonexistent")
    assert resp.status_code == 404


def test_update_connection_src_user(client, conn):
    resp = client.patch(
        f"/api/connections/{conn['id']}",
        json={"src_user": "alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["src_user"] == "alice"


def test_update_connection_dst_ip(client, conn):
    resp = client.patch(
        f"/api/connections/{conn['id']}",
        json={"dst_ip": "192.168.1.1"},
    )
    assert resp.status_code == 200
    assert resp.json()["dst_ip"] == "192.168.1.1"


def test_update_connection_type(client, conn):
    resp = client.patch(
        f"/api/connections/{conn['id']}",
        json={"connection_type": "scp"},
    )
    assert resp.status_code == 200
    assert resp.json()["connection_type"] == "scp"


def test_update_connection_multiple_fields(client, conn):
    resp = client.patch(
        f"/api/connections/{conn['id']}",
        json={
            "src_user": "newuser",
            "dst_user": "newdst",
            "source_file": "updated.log",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["src_user"] == "newuser"
    assert data["dst_user"] == "newdst"
    assert data["source_file"] == "updated.log"


def test_update_connection_not_found(client):
    resp = client.patch("/api/connections/bad-id", json={"src_user": "x"})
    assert resp.status_code == 404


def test_update_connection_nil_fields_unchanged(client, conn):
    """Sending no fields leaves the record unchanged."""
    resp = client.patch(f"/api/connections/{conn['id']}", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["src_user"] == "bob"
    assert data["dst_user"] == "root"


def test_delete_connection(client, op, conn):
    resp = client.delete(f"/api/connections/{conn['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/connections/{conn['id']}").status_code == 404
