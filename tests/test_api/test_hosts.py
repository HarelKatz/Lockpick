"""API tests for Hosts, HostIPs, and HostUsers endpoints."""
import pytest


@pytest.fixture
def op(client):
    """Create and return a test operation."""
    resp = client.post("/api/ops", json={"name": "Test Op"})
    return resp.json()


def test_create_host(client, op):
    resp = client.post(
        f"/api/ops/{op['id']}/hosts",
        json={"nickname": "web01", "comment": "Web server"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["nickname"] == "web01"
    assert data["comment"] == "Web server"
    assert data["op_id"] == op["id"]
    assert "id" in data


def test_create_host_minimal(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "db01"})
    assert resp.status_code == 201
    assert resp.json()["comment"] is None


def test_create_host_op_not_found(client):
    resp = client.post("/api/ops/bad-id/hosts", json={"nickname": "x"})
    assert resp.status_code == 404


def test_list_hosts(client, op):
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host1"})
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host2"})
    resp = client.get(f"/api/ops/{op['id']}/hosts")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_hosts_empty(client, op):
    resp = client.get(f"/api/ops/{op['id']}/hosts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_host(client, op):
    create_resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host1"})
    host_id = create_resp.json()["id"]
    resp = client.get(f"/api/hosts/{host_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == host_id


def test_get_host_includes_ips_and_users(client, op):
    create_resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host1"})
    host_id = create_resp.json()["id"]
    # Add an IP
    client.post(f"/api/hosts/{host_id}/ips", json={"ip_address": "10.0.0.1"})
    # Add a user
    client.post(f"/api/hosts/{host_id}/users", json={"username": "root"})
    resp = client.get(f"/api/hosts/{host_id}")
    data = resp.json()
    assert len(data["ips"]) == 1
    assert data["ips"][0]["ip_address"] == "10.0.0.1"
    assert len(data["users"]) == 1
    assert data["users"][0]["username"] == "root"


def test_update_host(client, op):
    create_resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "old"})
    host_id = create_resp.json()["id"]
    resp = client.patch(f"/api/hosts/{host_id}", json={"nickname": "new", "comment": "updated"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["nickname"] == "new"
    assert data["comment"] == "updated"


def test_delete_host(client, op):
    create_resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "todelete"})
    host_id = create_resp.json()["id"]
    resp = client.delete(f"/api/hosts/{host_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/hosts/{host_id}").status_code == 404


# ─── HostIP tests ─────────────────────────────────────────────────────────────

@pytest.fixture
def host(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "target"})
    return resp.json()


def test_add_host_ip(client, host):
    resp = client.post(
        f"/api/hosts/{host['id']}/ips",
        json={"ip_address": "192.168.1.100", "cidr": "24", "interface_name": "eth0"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ip_address"] == "192.168.1.100"
    assert data["cidr"] == "24"
    assert data["interface_name"] == "eth0"
    assert data["source"] == "manual"


def test_add_host_ip_minimal(client, host):
    resp = client.post(f"/api/hosts/{host['id']}/ips", json={"ip_address": "10.0.0.5"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["ip_address"] == "10.0.0.5"
    assert data["cidr"] is None


def test_list_host_ips(client, host):
    client.post(f"/api/hosts/{host['id']}/ips", json={"ip_address": "10.0.0.1"})
    client.post(f"/api/hosts/{host['id']}/ips", json={"ip_address": "10.0.0.2"})
    resp = client.get(f"/api/hosts/{host['id']}/ips")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_delete_host_ip(client, host):
    add_resp = client.post(f"/api/hosts/{host['id']}/ips", json={"ip_address": "1.2.3.4"})
    ip_id = add_resp.json()["id"]
    resp = client.delete(f"/api/hosts/{host['id']}/ips/{ip_id}")
    assert resp.status_code == 204


# ─── HostUser tests ───────────────────────────────────────────────────────────

def test_add_host_user(client, host):
    resp = client.post(
        f"/api/hosts/{host['id']}/users",
        json={"username": "bob", "shell": "/bin/bash", "home_dir": "/home/bob", "source": "passwd_file"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "bob"
    assert data["shell"] == "/bin/bash"
    assert data["source"] == "passwd_file"


def test_add_host_user_default_source(client, host):
    resp = client.post(f"/api/hosts/{host['id']}/users", json={"username": "alice"})
    assert resp.status_code == 201
    assert resp.json()["source"] == "manual"


def test_list_host_users(client, host):
    client.post(f"/api/hosts/{host['id']}/users", json={"username": "user1"})
    client.post(f"/api/hosts/{host['id']}/users", json={"username": "user2"})
    resp = client.get(f"/api/hosts/{host['id']}/users")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_delete_host_user(client, host):
    add_resp = client.post(f"/api/hosts/{host['id']}/users", json={"username": "temp"})
    user_id = add_resp.json()["id"]
    resp = client.delete(f"/api/hosts/{host['id']}/users/{user_id}")
    assert resp.status_code == 204
