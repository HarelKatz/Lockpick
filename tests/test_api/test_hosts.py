"""API tests for Hosts and HostIPs endpoints."""
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


def test_get_host_includes_ips(client, op):
    create_resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "host1"})
    host_id = create_resp.json()["id"]
    client.post(f"/api/hosts/{host_id}/ips", json={"ip_address": "10.0.0.1"})
    resp = client.get(f"/api/hosts/{host_id}")
    data = resp.json()
    assert len(data["ips"]) == 1
    assert data["ips"][0]["ip_address"] == "10.0.0.1"


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
        json={"ip_address": "192.168.1.100"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ip_address"] == "192.168.1.100"
    assert data["source"] == "manual"


def test_add_host_ip_minimal(client, host):
    resp = client.post(f"/api/hosts/{host['id']}/ips", json={"ip_address": "10.0.0.5"})
    assert resp.status_code == 201
    assert resp.json()["ip_address"] == "10.0.0.5"


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


# ─── Merge endpoint ──────────────────────────────────────────────────────────

def _two_hosts(client, op_id, src_nick="src", tgt_nick="tgt", src_comment=None,
               src_status=None, tgt_comment=None, tgt_status=None):
    src = client.post(
        f"/api/ops/{op_id}/hosts",
        json={"nickname": src_nick, "comment": src_comment},
    ).json()
    if src_status:
        client.patch(f"/api/hosts/{src['id']}", json={"status": src_status})
    tgt = client.post(
        f"/api/ops/{op_id}/hosts",
        json={"nickname": tgt_nick, "comment": tgt_comment},
    ).json()
    if tgt_status:
        client.patch(f"/api/hosts/{tgt['id']}", json={"status": tgt_status})
    return src["id"], tgt["id"]


def test_merge_happy_path(client, op):
    src_id, tgt_id = _two_hosts(client, op["id"])
    client.post(f"/api/hosts/{src_id}/ips", json={"ip_address": "10.0.0.5"})
    client.post(f"/api/hosts/{src_id}/users", json={"username": "bob"})

    resp = client.post(
        f"/api/hosts/{src_id}/merge",
        json={"target_host_id": tgt_id, "resolutions": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["target"]["id"] == tgt_id
    assert body["counts"]["ips_moved"] == 1
    assert body["counts"]["users_moved"] == 1

    # Source is gone, target now owns the relations.
    assert client.get(f"/api/hosts/{src_id}").status_code == 404
    target = client.get(f"/api/hosts/{tgt_id}").json()
    assert any(ip["ip_address"] == "10.0.0.5" for ip in target["ips"])
    assert any(u["username"] == "bob" for u in target["users"])

    # Activity log captures the merge.
    log = client.get(f"/api/ops/{op['id']}/activity").json()
    merge_entries = [e for e in log if e["action"] == "host.merge"]
    assert len(merge_entries) == 1
    assert merge_entries[0]["entity_id"] == tgt_id
    assert "Merged 'src' into 'tgt'" in merge_entries[0]["detail"]


def test_merge_resolution_pick_source_nickname(client, op):
    src_id, tgt_id = _two_hosts(client, op["id"], src_nick="prefer-this")
    resp = client.post(
        f"/api/hosts/{src_id}/merge",
        json={"target_host_id": tgt_id, "resolutions": {"nickname": "source"}},
    )
    assert resp.status_code == 200
    assert resp.json()["target"]["nickname"] == "prefer-this"


def test_merge_resolution_freetext_nickname(client, op):
    src_id, tgt_id = _two_hosts(client, op["id"])
    resp = client.post(
        f"/api/hosts/{src_id}/merge",
        json={"target_host_id": tgt_id, "resolutions": {"nickname": "frankenhost"}},
    )
    assert resp.status_code == 200
    assert resp.json()["target"]["nickname"] == "frankenhost"


def test_merge_resolution_pick_source_status(client, op):
    src_id, tgt_id = _two_hosts(
        client, op["id"], src_status="compromised", tgt_status="pivot",
    )
    resp = client.post(
        f"/api/hosts/{src_id}/merge",
        json={"target_host_id": tgt_id, "resolutions": {"status": "source"}},
    )
    assert resp.status_code == 200
    assert resp.json()["target"]["status"] == "compromised"


def test_merge_no_resolutions_keeps_target_values(client, op):
    src_id, tgt_id = _two_hosts(
        client, op["id"], src_comment="src note", tgt_comment="tgt note",
    )
    resp = client.post(
        f"/api/hosts/{src_id}/merge",
        json={"target_host_id": tgt_id, "resolutions": {}},
    )
    assert resp.status_code == 200
    target = resp.json()["target"]
    assert target["nickname"] == "tgt"
    assert target["comment"] == "tgt note"


def test_merge_self_returns_400(client, op):
    src_id, _ = _two_hosts(client, op["id"])
    resp = client.post(
        f"/api/hosts/{src_id}/merge",
        json={"target_host_id": src_id, "resolutions": {}},
    )
    assert resp.status_code == 400
    assert "differ" in resp.json()["detail"]


def test_merge_cross_op_returns_400(client):
    op_a = client.post("/api/ops", json={"name": "A"}).json()
    op_b = client.post("/api/ops", json={"name": "B"}).json()
    src = client.post(f"/api/ops/{op_a['id']}/hosts", json={"nickname": "s"}).json()
    tgt = client.post(f"/api/ops/{op_b['id']}/hosts", json={"nickname": "t"}).json()

    resp = client.post(
        f"/api/hosts/{src['id']}/merge",
        json={"target_host_id": tgt["id"], "resolutions": {}},
    )
    assert resp.status_code == 400
    assert "same operation" in resp.json()["detail"]


def test_merge_source_not_found_returns_404(client, op):
    tgt = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "t"}).json()
    resp = client.post(
        "/api/hosts/deadbeef-no-such-host/merge",
        json={"target_host_id": tgt["id"], "resolutions": {}},
    )
    assert resp.status_code == 404


def test_merge_target_not_found_returns_404(client, op):
    src = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "s"}).json()
    resp = client.post(
        f"/api/hosts/{src['id']}/merge",
        json={"target_host_id": "deadbeef-no-target", "resolutions": {}},
    )
    assert resp.status_code == 404


def test_merge_rejects_empty_nickname(client, op):
    """Empty / whitespace-only nickname must be rejected at the boundary —
    the frontend disables submit, but the endpoint itself should not
    trust client-side validation."""
    src_id, tgt_id = _two_hosts(client, op["id"])
    for bad in ("", "   ", "\t"):
        resp = client.post(
            f"/api/hosts/{src_id}/merge",
            json={"target_host_id": tgt_id, "resolutions": {"nickname": bad}},
        )
        assert resp.status_code == 422, f"expected 422 for nickname={bad!r}"


# ─── addr_type is always inferred from the value (Architecture Rule #16) ──────

def test_add_host_ip_infers_ipv6(client, host):
    resp = client.post(f"/api/hosts/{host['id']}/ips", json={"ip_address": "2001:db8::1"})
    assert resp.status_code == 201
    assert resp.json()["addr_type"] == "ipv6"


def test_add_host_ip_infers_hostname(client, host):
    resp = client.post(f"/api/hosts/{host['id']}/ips", json={"ip_address": "web01.corp.local"})
    assert resp.status_code == 201
    assert resp.json()["addr_type"] == "hostname"


def test_add_host_ip_infers_ipv4(client, host):
    resp = client.post(f"/api/hosts/{host['id']}/ips", json={"ip_address": "10.1.2.3"})
    assert resp.status_code == 201
    assert resp.json()["addr_type"] == "ipv4"


def test_add_host_ip_ignores_client_supplied_addr_type(client, host):
    """A client-sent addr_type is ignored — the stored type is inferred from the value."""
    resp = client.post(
        f"/api/hosts/{host['id']}/ips",
        json={"ip_address": "2001:db8::2", "addr_type": "ipv4"},
    )
    assert resp.status_code == 201
    assert resp.json()["addr_type"] == "ipv6"


# ─── OS / kernel inventory metadata ───────────────────────────────────────────

def test_create_host_os_and_kernel_default_to_none(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "bare01"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["os_version"] is None
    assert data["kernel_version"] is None


def test_create_host_with_os_and_kernel(client, op):
    resp = client.post(f"/api/ops/{op['id']}/hosts", json={
        "nickname": "web01",
        "os_version": "Ubuntu 22.04.3 LTS",
        "kernel_version": "5.15.0-88-generic",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["os_version"] == "Ubuntu 22.04.3 LTS"
    assert data["kernel_version"] == "5.15.0-88-generic"


def test_update_host_os_and_kernel(client, op):
    host_id = client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "web01"}).json()["id"]
    resp = client.patch(f"/api/hosts/{host_id}", json={
        "os_version": "Debian GNU/Linux 12 (bookworm)",
        "kernel_version": "6.1.0-13-amd64",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["os_version"] == "Debian GNU/Linux 12 (bookworm)"
    assert data["kernel_version"] == "6.1.0-13-amd64"


def test_update_host_omitting_os_leaves_it_intact(client, op):
    host_id = client.post(f"/api/ops/{op['id']}/hosts", json={
        "nickname": "web01", "os_version": "Ubuntu 22.04", "kernel_version": "5.15.0",
    }).json()["id"]
    resp = client.patch(f"/api/hosts/{host_id}", json={"comment": "renamed only"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["os_version"] == "Ubuntu 22.04"
    assert data["kernel_version"] == "5.15.0"


@pytest.mark.parametrize("field", ["os_version", "kernel_version"])
def test_update_host_can_clear_inventory_field_with_null(client, op, field):
    host_id = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "web01", field: "something"}
    ).json()["id"]
    resp = client.patch(f"/api/hosts/{host_id}", json={field: None})
    assert resp.status_code == 200
    assert resp.json()[field] is None
