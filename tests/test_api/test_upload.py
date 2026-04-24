"""Integration tests for the file upload endpoint."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _create_op(client) -> str:
    r = client.post("/api/ops", json={"name": "TestOp"})
    assert r.status_code == 201
    return r.json()["id"]


def _create_host(client, op_id: str, nickname: str = "web01") -> str:
    r = client.post(f"/api/ops/{op_id}/hosts", json={"nickname": nickname})
    assert r.status_code == 201
    return r.json()["id"]


def test_upload_authorized_keys(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "authorized_keys").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "authorized_keys", "host_id": host_id, "username": "alice"},
        files={"file": ("authorized_keys", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["summary"]["new_credentials"] == 3
    assert body["file_type"] == "authorized_keys"


def test_upload_known_hosts(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "known_hosts").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "known_hosts", "host_id": host_id, "username": "bob"},
        files={"file": ("known_hosts", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["summary"]["new_connections"] == 4


def test_upload_bash_history(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "bash_history").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "bash_history", "host_id": host_id, "username": "alice"},
        files={"file": (".bash_history", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["new_connections"] == 7


def test_upload_passwd(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "passwd").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "passwd", "host_id": host_id},
        files={"file": ("passwd", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    # no credentials or connections from passwd
    assert body["summary"]["new_credentials"] == 0
    assert body["summary"]["new_connections"] == 0


def test_upload_auth_log(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "auth.log").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "auth_log", "host_id": host_id},
        files={"file": ("auth.log", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["new_connections"] == 2


def test_upload_private_key(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "id_rsa").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "private_key", "host_id": host_id, "username": "alice"},
        files={"file": ("id_rsa", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["new_credentials"] == 1


def test_pivot_detection(client, tmp_path):
    """Upload a private key, then an authorized_keys with the matching public key — expect pivot message."""
    op_id = _create_op(client)
    hostA_id = _create_host(client, op_id, "hostA")
    hostB_id = _create_host(client, op_id, "hostB")

    # Upload private key to hostA
    priv_content = (FIXTURES / "id_rsa").read_bytes()
    r1 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "private_key", "host_id": hostA_id, "username": "alice"},
        files={"file": ("id_rsa", priv_content, "text/plain")},
    )
    assert r1.status_code == 200

    # Upload authorized_keys to hostB containing the matching public key
    pub_line = (FIXTURES / "id_rsa.pub").read_text().strip()
    auth_keys_content = (pub_line + "\n").encode()
    r2 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "authorized_keys", "host_id": hostB_id, "username": "root"},
        files={"file": ("authorized_keys", auth_keys_content, "text/plain")},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert len(body["pivot_opportunities"]) == 1
    assert "hostA" in body["pivot_opportunities"][0]
    assert "hostB" in body["pivot_opportunities"][0]


def test_nmap_upload_new_hosts_in_stats(client):
    """Nmap uploads must report discovered hosts in new_hosts (Fix 1: new_discovered_hosts added to stats)."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "nmap_scan.xml").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "nmap_xml", "host_id": host_id},
        files={"file": ("nmap_scan.xml", content, "application/xml")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    # nmap_scan.xml has 3 "up" hosts; the dual-stack host emits 2 IPs → 4 HostData records total
    assert body["summary"]["new_hosts"] == 4


def test_nmap_upload_sets_nickname_from_hostname(client):
    """Nmap-discovered hosts must get their hostname as nickname (Fix: use Auto-created guard)."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = (FIXTURES / "nmap_scan.xml").read_bytes()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "nmap_xml", "host_id": host_id},
        files={"file": ("nmap_scan.xml", content, "application/xml")},
    )
    assert resp.status_code == 200

    hosts_resp = client.get(f"/api/ops/{op_id}/hosts")
    assert hosts_resp.status_code == 200
    hosts = hosts_resp.json()
    nicknames = {h["nickname"] for h in hosts}

    # nmap_scan.xml contains webserver.corp.local (10.0.0.5) and dbserver.corp.local (10.0.0.20)
    assert "webserver.corp.local" in nicknames, f"Expected webserver.corp.local in {nicknames}"
    assert "dbserver.corp.local" in nicknames, f"Expected dbserver.corp.local in {nicknames}"


def test_credential_link_dedup_includes_username(client):
    """Same key uploaded for two different users on the same host must create 2 CredentialLinks (Fix 3)."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    pub_line = (FIXTURES / "id_rsa.pub").read_text().strip()
    key_content = (pub_line + "\n").encode()

    # Upload the same public key as bob
    r1 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "authorized_keys", "host_id": host_id, "username": "bob"},
        files={"file": ("authorized_keys", key_content, "text/plain")},
    )
    assert r1.status_code == 200
    assert r1.json()["summary"]["new_credential_links"] == 1

    # Upload the same public key as alice — should create a second link, not be suppressed
    r2 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "authorized_keys", "host_id": host_id, "username": "alice"},
        files={"file": ("authorized_keys", key_content, "text/plain")},
    )
    assert r2.status_code == 200
    assert r2.json()["summary"]["new_credential_links"] == 1

    # Verify exactly 1 Credential record was created (deduped)
    creds_resp = client.get(f"/api/ops/{op_id}/credentials")
    assert creds_resp.status_code == 200
    assert len(creds_resp.json()) == 1

    # Verify 2 CredentialLinks exist (bob + alice)
    links_resp = client.get(f"/api/ops/{op_id}/credential-links")
    assert links_resp.status_code == 200
    links = links_resp.json()
    host_links = [lk for lk in links if lk.get("host_id") == host_id]
    assert len(host_links) == 2, f"Expected 2 links (bob + alice), got {len(host_links)}: {host_links}"
    usernames = {lk["username"] for lk in host_links}
    assert usernames == {"bob", "alice"}


def test_invalid_file_type(client, tmp_path):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "not_a_type", "host_id": host_id},
        files={"file": ("foo", b"data", "text/plain")},
    )
    assert resp.status_code == 422


def test_upload_op_not_found(client):
    resp = client.post(
        "/api/ops/nonexistent/upload",
        data={"file_type": "passwd", "host_id": "x"},
        files={"file": ("f", b"", "text/plain")},
    )
    assert resp.status_code == 404


# ─── Priority 1: etc_hosts API integration (BUG-01) ──────────────────────────

def test_etc_hosts_upload_creates_hosts(client):
    """etc_hosts upload must persist discovered hosts (BUG-01 fix: hosts_found is consumed)."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    # Minimal etc_hosts with 2 unique IPs — simple, predictable fixture
    content = b"10.10.0.1  web-server\n10.10.0.2  db-server\n"
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "etc_hosts", "host_id": host_id},
        files={"file": ("etc_hosts", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True

    # Both IPs + their hostname aliases should create hosts.
    # etc_hosts parser emits one HostData per IP and one per hostname.
    # 2 IPs + 2 hostnames = 4 HostData records → 4 new hosts.
    assert body["summary"]["new_hosts"] == 4

    # Verify hosts are actually in the DB (total = 1 upload host + 4 new)
    hosts_resp = client.get(f"/api/ops/{op_id}/hosts")
    assert hosts_resp.status_code == 200
    assert len(hosts_resp.json()) == 5


def test_etc_hosts_upload_loopback_skipped(client):
    """etc_hosts loopback entries must not create new hosts."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = b"127.0.0.1  localhost\n::1  localhost\n10.0.0.5  realhost\n"
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "etc_hosts", "host_id": host_id},
        files={"file": ("etc_hosts", content, "text/plain")},
    )
    assert resp.status_code == 200
    # Only 1 IP + 1 hostname for realhost; loopbacks skipped → 2 new hosts
    assert resp.json()["summary"]["new_hosts"] == 2


# ─── Priority 2: Re-upload dedup: same key in two files → 1 cred, 2 links ────

def test_reupload_same_key_to_two_hosts_deduplicates_credential(client):
    """Upload the same private key to host A and host B: 1 Credential, 2 CredentialLinks."""
    op_id = _create_op(client)
    host_a_id = _create_host(client, op_id, "hostA")
    host_b_id = _create_host(client, op_id, "hostB")

    priv_content = (FIXTURES / "id_rsa").read_bytes()

    # Upload to hostA
    r1 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "private_key", "host_id": host_a_id, "username": "alice"},
        files={"file": ("id_rsa", priv_content, "text/plain")},
    )
    assert r1.status_code == 200
    assert r1.json()["summary"]["new_credentials"] == 1
    assert r1.json()["summary"]["new_credential_links"] == 1

    # Upload same key to hostB
    r2 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "private_key", "host_id": host_b_id, "username": "bob"},
        files={"file": ("id_rsa", priv_content, "text/plain")},
    )
    assert r2.status_code == 200
    # Credential deduped — no new credential
    assert r2.json()["summary"]["new_credentials"] == 0
    # But a new link is created for hostB
    assert r2.json()["summary"]["new_credential_links"] == 1

    # Verify: exactly 1 Credential in the op
    creds = client.get(f"/api/ops/{op_id}/credentials").json()
    assert len(creds) == 1

    # Verify: exactly 2 CredentialLinks (one per host)
    links = client.get(f"/api/ops/{op_id}/credential-links").json()
    assert len(links) == 2
    host_ids = {lk["host_id"] for lk in links}
    assert host_ids == {host_a_id, host_b_id}


# ─── Priority 3: Reverse-order pivot detection ────────────────────────────────

def test_reverse_pivot_detection(client):
    """Upload authorized_keys to hostB first, then private key to hostA — pivot must be found."""
    op_id = _create_op(client)
    host_a_id = _create_host(client, op_id, "hostA")
    host_b_id = _create_host(client, op_id, "hostB")

    # Upload authorized_keys (containing matching public key) to hostB FIRST
    pub_line = (FIXTURES / "id_rsa.pub").read_text().strip()
    auth_keys_content = (pub_line + "\n").encode()
    r1 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "authorized_keys", "host_id": host_b_id, "username": "root"},
        files={"file": ("authorized_keys", auth_keys_content, "text/plain")},
    )
    assert r1.status_code == 200
    # No pivot yet — private key not seen
    assert r1.json()["pivot_opportunities"] == []

    # Now upload private key to hostA
    priv_content = (FIXTURES / "id_rsa").read_bytes()
    r2 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "private_key", "host_id": host_a_id, "username": "alice"},
        files={"file": ("id_rsa", priv_content, "text/plain")},
    )
    assert r2.status_code == 200
    pivots = r2.json()["pivot_opportunities"]
    assert len(pivots) == 1
    # The pivot message must reference both hosts
    assert "hostA" in pivots[0]
    assert "hostB" in pivots[0]


# ─── Priority 6: Loopback routing ─────────────────────────────────────────────

def test_loopback_routes_to_upload_host(client):
    """Loopback IP in auth.log must route to the upload host, not create a new host.

    The bash_history parser skips loopback addresses at parse time (they're in
    _SKIP_HOSTS and never emitted as ConnectionData). The loopback routing in
    the upload router handles parsers like auth_log that DO emit loopback src IPs.
    """
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    # auth.log line where the SSH connection came FROM 127.0.0.1 (loopback)
    # This simulates a local SSH (e.g. sshd on same host forwarding to itself).
    content = b"Jan 15 10:00:01 host sshd[1234]: Accepted publickey for root from 127.0.0.1 port 12345 ssh2\n"
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "auth_log", "host_id": host_id},
        files={"file": ("auth.log", content, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["summary"]["new_connections"] == 1

    # Verify the connection record: src_host_id must be the upload host (loopback → self)
    conns = client.get(f"/api/ops/{op_id}/connections").json()
    assert len(conns) == 1
    conn = conns[0]
    assert conn["src_host_id"] == host_id, (
        f"Expected src_host_id={host_id} (loopback→upload host), got {conn['src_host_id']}"
    )
    # No new host should have been created (total = 1, the upload host)
    hosts = client.get(f"/api/ops/{op_id}/hosts").json()
    assert len(hosts) == 1


# ─── Priority 15: _get_or_create_host_user update path ───────────────────────

def test_host_user_gains_shell_on_reupload(client):
    """Re-uploading a passwd file that adds shell/home_dir updates existing HostUser records."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    # First upload: authorized_keys creates a HostUser with no shell/home_dir
    pub_line = (FIXTURES / "id_rsa.pub").read_text().strip()
    r1 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "authorized_keys", "host_id": host_id, "username": "alice"},
        files={"file": ("authorized_keys", (pub_line + "\n").encode(), "text/plain")},
    )
    assert r1.status_code == 200

    # Verify HostUser was created without shell
    users_resp = client.get(f"/api/hosts/{host_id}/users")
    assert users_resp.status_code == 200
    users = users_resp.json()
    alice = next((u for u in users if u["username"] == "alice"), None)
    assert alice is not None
    assert alice["shell"] is None

    # Second upload: passwd file adds shell and home_dir for alice
    passwd_content = b"alice:x:1001:1001::/home/alice:/bin/bash\n"
    r2 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "passwd", "host_id": host_id},
        files={"file": ("passwd", passwd_content, "text/plain")},
    )
    assert r2.status_code == 200

    # HostUser should now have shell and home_dir
    users_resp2 = client.get(f"/api/hosts/{host_id}/users")
    users2 = users_resp2.json()
    alice2 = next((u for u in users2 if u["username"] == "alice"), None)
    assert alice2 is not None
    # Only one alice record (not duplicated)
    alice_records = [u for u in users2 if u["username"] == "alice"]
    assert len(alice_records) == 1
    assert alice2["shell"] == "/bin/bash"
    assert alice2["home_dir"] == "/home/alice"


# ─── Priority 16: public_key file_type ────────────────────────────────────────

def test_upload_public_key_file_type(client):
    """file_type=public_key must be accepted and create a credential with fingerprint."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    pub_line = (FIXTURES / "id_rsa.pub").read_text().strip()
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "public_key", "host_id": host_id, "username": "alice"},
        files={"file": ("id_rsa.pub", (pub_line + "\n").encode(), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["summary"]["new_credentials"] == 1

    # Credential must have a fingerprint (same as the private key's fingerprint)
    creds = client.get(f"/api/ops/{op_id}/credentials").json()
    assert len(creds) == 1
    assert creds[0]["fingerprint"] is not None
    assert creds[0]["fingerprint"].startswith("SHA256:")


# ─── Priority 25: Upload with host belonging to different op ──────────────────

def test_upload_host_in_wrong_op_returns_404(client):
    """Upload to an op_id where the host_id belongs to a different op must return 404."""
    op1_id = _create_op(client)
    op2_id = _create_op(client)
    host_in_op2 = _create_host(client, op2_id, "foreign-host")

    # Try to upload to op1 but specify a host that belongs to op2
    resp = client.post(
        f"/api/ops/{op1_id}/upload",
        data={"file_type": "bash_history", "host_id": host_in_op2},
        files={"file": (".bash_history", b"ssh root@10.0.0.1\n", "text/plain")},
    )
    assert resp.status_code == 404
