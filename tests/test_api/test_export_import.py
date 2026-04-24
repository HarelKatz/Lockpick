"""API tests for export and import endpoints."""
import pytest


@pytest.fixture
def op(client):
    resp = client.post("/api/ops", json={"name": "Test Op"})
    return resp.json()


# ─── Export ───────────────────────────────────────────────────────────────────

def test_export_op_not_found(client):
    resp = client.get("/api/ops/bad-id/export")
    assert resp.status_code == 404


def test_export_empty_op(client, op):
    resp = client.get(f"/api/ops/{op['id']}/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hosts"] == []
    assert data["credentials"] == []
    assert data["connections"] == []


def test_export_has_version_field(client, op):
    resp = client.get(f"/api/ops/{op['id']}/export")
    assert resp.status_code == 200
    assert resp.json()["lockpick_export_version"] == 1


def test_export_has_content_disposition_header(client, op):
    resp = client.get(f"/api/ops/{op['id']}/export")
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert cd.startswith("attachment")


def test_export_includes_host(client, op):
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "export-host"})
    resp = client.get(f"/api/ops/{op['id']}/export")
    assert resp.status_code == 200
    hosts = resp.json()["hosts"]
    assert len(hosts) == 1
    assert hosts[0]["nickname"] == "export-host"


def test_export_includes_credential(client, op):
    client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "password", "value": "s3cr3t"},
    )
    resp = client.get(f"/api/ops/{op['id']}/export")
    assert resp.status_code == 200
    creds = resp.json()["credentials"]
    assert len(creds) == 1
    assert creds[0]["value"] == "s3cr3t"


def test_export_includes_connection(client, op):
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_ip": "10.0.0.1",
            "dst_ip": "10.0.0.2",
            "direction_context": "from_src_logs",
            "source_file": "bash_history",
        },
    )
    resp = client.get(f"/api/ops/{op['id']}/export")
    assert resp.status_code == 200
    conns = resp.json()["connections"]
    assert len(conns) == 1
    assert conns[0]["src_ip"] == "10.0.0.1"


# ─── Import ───────────────────────────────────────────────────────────────────

def test_import_empty_export_creates_op(client, op):
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    resp = client.post("/api/ops/import", json={"data": export_data})
    assert resp.status_code == 201
    body = resp.json()
    assert "op_id" in body
    # The new op must be fetchable
    new_op_id = body["op_id"]
    get_resp = client.get(f"/api/ops/{new_op_id}")
    assert get_resp.status_code == 200


def test_import_name_override(client, op):
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    resp = client.post(
        "/api/ops/import",
        json={"data": export_data, "name_override": "custom"},
    )
    assert resp.status_code == 201
    assert resp.json()["op_name"] == "custom"


def test_import_default_name_appends_imported(client):
    orig_op = client.post("/api/ops", json={"name": "Orig"}).json()
    export_data = client.get(f"/api/ops/{orig_op['id']}/export").json()
    resp = client.post("/api/ops/import", json={"data": export_data})
    assert resp.status_code == 201
    assert resp.json()["op_name"] == "Orig (imported)"


def test_import_remaps_ids(client, op):
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    resp = client.post("/api/ops/import", json={"data": export_data})
    assert resp.status_code == 201
    new_op_id = resp.json()["op_id"]
    # New ID must differ from the original
    assert new_op_id != op["id"]
    # New op is reachable
    assert client.get(f"/api/ops/{new_op_id}").status_code == 200


def test_import_with_host_creates_host(client, op):
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "pivotbox"})
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201
    new_op_id = import_resp.json()["op_id"]
    hosts = client.get(f"/api/ops/{new_op_id}/hosts").json()
    assert len(hosts) == 1
    assert hosts[0]["nickname"] == "pivotbox"


def test_import_with_credential_creates_credential(client, op):
    client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "password", "value": "letmein", "name": "root_pw"},
    )
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201
    new_op_id = import_resp.json()["op_id"]
    creds = client.get(f"/api/ops/{new_op_id}/credentials").json()
    assert len(creds) == 1
    assert creds[0]["value"] == "letmein"


def test_import_with_connection_creates_connection(client, op):
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_ip": "172.16.0.1",
            "dst_ip": "172.16.0.2",
            "direction_context": "from_dst_logs",
            "source_file": "auth.log",
        },
    )
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201
    new_op_id = import_resp.json()["op_id"]
    conns = client.get(f"/api/ops/{new_op_id}/connections").json()
    assert len(conns) == 1
    assert conns[0]["src_ip"] == "172.16.0.1"


def test_import_invalid_body_returns_422(client):
    resp = client.post("/api/ops/import", json={})
    assert resp.status_code == 422


def test_roundtrip_export_import_export(client, op):
    # Populate the original op with one of each entity type
    host_resp = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "roundtrip-host"}
    )
    host_id = host_resp.json()["id"]
    client.post(f"/api/hosts/{host_id}/ips", json={"ip_address": "10.99.0.1"})
    client.post(
        f"/api/ops/{op['id']}/credentials",
        json={"cred_type": "password", "value": "rtpass"},
    )
    client.post(
        f"/api/ops/{op['id']}/connections",
        json={
            "src_ip": "10.99.0.1",
            "dst_ip": "10.99.0.2",
            "direction_context": "from_src_logs",
            "source_file": "bash_history",
        },
    )

    # First export
    first_export = client.get(f"/api/ops/{op['id']}/export").json()
    assert len(first_export["hosts"]) == 1
    assert len(first_export["credentials"]) == 1
    assert len(first_export["connections"]) == 1

    # Import
    import_resp = client.post("/api/ops/import", json={"data": first_export})
    assert import_resp.status_code == 201
    new_op_id = import_resp.json()["op_id"]

    # Second export from the imported op
    second_export = client.get(f"/api/ops/{new_op_id}/export").json()

    # Entity counts must be preserved
    assert len(second_export["hosts"]) == len(first_export["hosts"])
    assert len(second_export["credentials"]) == len(first_export["credentials"])
    assert len(second_export["connections"]) == len(first_export["connections"])


def test_roundtrip_addr_type_preserved(client, op):
    """addr_type on HostIP must survive export → import unchanged."""
    host_id = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "hostname-host"}
    ).json()["id"]
    client.post(
        f"/api/hosts/{host_id}/ips",
        json={"ip_address": "box.example.com", "addr_type": "hostname"},
    )

    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201
    new_op_id = import_resp.json()["op_id"]

    hosts = client.get(f"/api/ops/{new_op_id}/hosts").json()
    assert len(hosts) == 1
    ips = hosts[0]["ips"]
    assert len(ips) == 1
    assert ips[0]["addr_type"] == "hostname"


def test_roundtrip_host_status_preserved(client, op):
    """Host.status must survive export → import unchanged."""
    host_id = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "pwned"}
    ).json()["id"]
    client.patch(f"/api/hosts/{host_id}", json={"status": "compromised"})

    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201
    new_op_id = import_resp.json()["op_id"]

    hosts = client.get(f"/api/ops/{new_op_id}/hosts").json()
    assert len(hosts) == 1
    assert hosts[0]["status"] == "compromised"


def test_import_old_export_without_addr_type(client, op):
    """Importing an export that lacks addr_type must succeed (backwards compat)."""
    host_id = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "legacy-host"}
    ).json()["id"]
    client.post(f"/api/hosts/{host_id}/ips", json={"ip_address": "10.1.2.3"})

    export_data = client.get(f"/api/ops/{op['id']}/export").json()

    # Simulate a pre-fix export by stripping addr_type from every HostIP
    for host in export_data["hosts"]:
        for ip in host["ips"]:
            ip.pop("addr_type", None)

    resp = client.post("/api/ops/import", json={"data": export_data})
    assert resp.status_code == 201
