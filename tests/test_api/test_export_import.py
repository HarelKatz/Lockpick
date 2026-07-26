"""API tests for export and import endpoints."""
import pathlib

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


def test_roundtrip_summary_and_briefing_preserved(client, op):
    """Operation.summary/briefing must survive export → import unchanged."""
    client.patch(f"/api/ops/{op['id']}", json={
        "summary": "3 footholds, DC not reached.",
        "briefing": "## Rules of engagement\n\n- No DoS\n- 09:00-17:00 only",
    })

    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    assert export_data["operation"]["summary"] == "3 footholds, DC not reached."

    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201
    new_op_id = import_resp.json()["op_id"]

    imported = client.get(f"/api/ops/{new_op_id}").json()
    assert imported["summary"] == "3 footholds, DC not reached."
    assert imported["briefing"] == "## Rules of engagement\n\n- No DoS\n- 09:00-17:00 only"


def test_import_old_export_without_summary_and_briefing(client, op):
    """Importing a pre-briefing-fields export must succeed (backwards compat)."""
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    export_data["operation"].pop("summary", None)
    export_data["operation"].pop("briefing", None)

    resp = client.post("/api/ops/import", json={"data": export_data})
    assert resp.status_code == 201
    imported = client.get(f"/api/ops/{resp.json()['op_id']}").json()
    assert imported["summary"] is None
    assert imported["briefing"] is None


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


# ─── Priority 8: Export/import drops SudoRule, SshConfigPattern, HostNote ────

def test_export_import_drops_sudo_rules(client, op):
    """Sudo rules are not exported — imported op must have 0 sudo rules.

    NOTE: This documents a known limitation of the export format (lockpick_export_version: 1).
    SudoRule records are not included in the export schema and will be silently
    dropped on roundtrip. Callers should not rely on sudo rules surviving export/import.
    """
    fixtures = pathlib.Path(__file__).parent.parent / "fixtures"

    host_id = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "sudo-host"}
    ).json()["id"]

    # Upload sudoers to create SudoRule records
    sudoers_content = b"root ALL=(ALL:ALL) ALL\nalice ALL=(ALL) NOPASSWD: /usr/bin/apt\n"
    resp = client.post(
        f"/api/ops/{op['id']}/upload",
        data={"file_type": "sudoers", "host_id": host_id},
        files={"file": ("sudoers", sudoers_content, "text/plain")},
    )
    assert resp.status_code == 200

    # Verify sudo rules exist in the original op
    sudo_resp = client.get(f"/api/hosts/{host_id}/sudo-rules")
    assert sudo_resp.status_code == 200
    original_sudo_count = len(sudo_resp.json())
    assert original_sudo_count > 0, "Test setup: expected sudoers to create at least one sudo rule"

    # Export and import
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201
    new_op_id = import_resp.json()["op_id"]

    # Find the imported host by nickname
    new_hosts = client.get(f"/api/ops/{new_op_id}/hosts").json()
    new_host = next((h for h in new_hosts if h["nickname"] == "sudo-host"), None)
    assert new_host is not None

    # KNOWN LIMITATION: sudo rules are not exported — imported op has 0 sudo rules
    new_sudo_resp = client.get(f"/api/hosts/{new_host['id']}/sudo-rules")
    assert new_sudo_resp.status_code == 200
    assert len(new_sudo_resp.json()) == 0, (
        "Sudo rules must be absent after import — known limitation of export format v1"
    )


def test_export_import_drops_host_notes(client, op):
    """Host notes are not exported — imported op must have 0 notes.

    NOTE: This documents a known limitation of the export format (lockpick_export_version: 1).
    HostNote records are not included in the export schema and will be silently
    dropped on roundtrip.
    """
    host_id = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "noted-host"}
    ).json()["id"]

    # Add a note to the host
    note_resp = client.post(
        f"/api/hosts/{host_id}/notes",
        json={"content": "This is a test note"},
    )
    assert note_resp.status_code == 201

    # Verify the note exists
    notes = client.get(f"/api/hosts/{host_id}/notes").json()
    assert len(notes) == 1

    # Export and import
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201
    new_op_id = import_resp.json()["op_id"]

    # Find the imported host
    new_hosts = client.get(f"/api/ops/{new_op_id}/hosts").json()
    new_host = next((h for h in new_hosts if h["nickname"] == "noted-host"), None)
    assert new_host is not None

    # KNOWN LIMITATION: notes are not exported
    new_notes = client.get(f"/api/hosts/{new_host['id']}/notes").json()
    assert len(new_notes) == 0, (
        "Host notes must be absent after import — known limitation of export format v1"
    )


def test_export_import_preserves_pattern_connection_records(client, op):
    """ConnectionRecords from SSH config patterns ARE exported; SshConfigPattern table is not.

    NOTE: This documents a known limitation of the export format (lockpick_export_version: 1).
    SshConfigPattern records are not in the export schema. Any retroactive edges
    from pattern matching are also lost on import.
    """
    host_id = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "jump-host"}
    ).json()["id"]

    # Upload ssh_config with a wildcard pattern
    ssh_config_content = b"Host *.internal\n  User alice\n  Port 22\n"
    resp = client.post(
        f"/api/ops/{op['id']}/upload",
        data={"file_type": "ssh_config", "host_id": host_id},
        files={"file": ("config", ssh_config_content, "text/plain")},
    )
    assert resp.status_code == 200

    # Verify pattern is stored (add a matching host to confirm pattern worked)
    matching_host_id = client.post(
        f"/api/ops/{op['id']}/hosts", json={"nickname": "web.internal"}
    ).json()["id"]
    conns_before = client.get(f"/api/ops/{op['id']}/connections").json()
    pattern_conns = [c for c in conns_before if c.get("source_file") == "ssh_config_pattern"]
    assert len(pattern_conns) == 1, "Pattern must create 1 connection before export"

    # Export and import
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201
    new_op_id = import_resp.json()["op_id"]

    # KNOWN LIMITATION: patterns are not in export schema.
    # The imported op will have the connection records (connections ARE exported)
    # but if a new host is added, patterns won't retroactively apply.
    # Verify connections were preserved (they ARE exported):
    new_conns = client.get(f"/api/ops/{new_op_id}/connections").json()
    pattern_new_conns = [c for c in new_conns if c.get("source_file") == "ssh_config_pattern"]
    # ConnectionRecords ARE exported, so the existing connection survives.
    # But adding new hosts won't trigger pattern matching since patterns aren't stored.
    assert len(pattern_new_conns) == 1, (
        "Connection records from patterns ARE exported (connections table is included); "
        "but SshConfigPattern table itself is not — new hosts added after import won't match"
    )


def test_roundtrip_host_os_and_kernel_preserved(client, op):
    """Host.os_version / kernel_version must survive export → import unchanged."""
    client.post(f"/api/ops/{op['id']}/hosts", json={
        "nickname": "web01",
        "os_version": "Ubuntu 22.04.3 LTS",
        "kernel_version": "5.15.0-88-generic",
    })

    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201

    hosts = client.get(f"/api/ops/{import_resp.json()['op_id']}/hosts").json()
    assert len(hosts) == 1
    assert hosts[0]["os_version"] == "Ubuntu 22.04.3 LTS"
    assert hosts[0]["kernel_version"] == "5.15.0-88-generic"


def test_import_old_export_without_host_os_and_kernel(client, op):
    """Importing a pre-inventory-fields export must succeed (backwards compat)."""
    client.post(f"/api/ops/{op['id']}/hosts", json={"nickname": "legacy01"})
    export_data = client.get(f"/api/ops/{op['id']}/export").json()
    for host in export_data["hosts"]:
        host.pop("os_version", None)
        host.pop("kernel_version", None)

    resp = client.post("/api/ops/import", json={"data": export_data})
    assert resp.status_code == 201
    hosts = client.get(f"/api/ops/{resp.json()['op_id']}/hosts").json()
    assert hosts[0]["os_version"] is None
