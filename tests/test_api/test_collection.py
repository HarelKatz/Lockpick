"""Integration tests for the collection-script + archive-import endpoints."""
import io
import json
import os
import sys
import tarfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _create_op(client, name: str = "TestOp") -> str:
    r = client.post("/api/ops", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


def _create_host(client, op_id: str, nickname: str = "web01") -> str:
    r = client.post(f"/api/ops/{op_id}/hosts", json={"nickname": nickname})
    assert r.status_code == 201
    return r.json()["id"]


def _build_tarball(
    entries: dict[str, bytes],
    include_manifest: bool = True,
) -> bytes:
    """Build a .tar.gz in-memory from a {filename: bytes} map."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in entries.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = int(time.time())
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
        if include_manifest and "manifest.json" not in entries:
            manifest = {
                "generated_at_utc": "2026-01-01T00:00:00Z",
                "hostname": "testhost",
                "invoking_user": "tester",
                "files": [
                    {"filename": name, "file_type": name.split("__", 1)[0] if "__" in name else "",
                     "username": name.split("__", 1)[1].rsplit(".", 1)[0] if "__" in name else "",
                     "source_path": f"/tmp/{name}", "stderr_present": False}
                    for name in entries.keys()
                ],
            }
            manifest_bytes = json.dumps(manifest).encode()
            info = tarfile.TarInfo(name="manifest.json")
            info.size = len(manifest_bytes)
            info.mtime = int(time.time())
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(manifest_bytes))
    return buf.getvalue()


def _build_raw_tarball(members: list[tarfile.TarInfo], payloads: dict[str, bytes]) -> bytes:
    """Lower-level builder — caller constructs TarInfo instances directly (for malicious cases)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for info in members:
            data = payloads.get(info.name, b"")
            info.size = len(data)
            info.mtime = int(time.time())
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# ─── GET /collection-script ──────────────────────────────────────────────────

def test_collection_script_basic(client):
    op_id = _create_op(client)
    r = client.get(f"/api/ops/{op_id}/collection-script")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/x-shellscript")
    body = r.text
    assert body.startswith("#!/usr/bin/env bash")
    # Sanity: body references the filename convention the import side parses
    assert "<file_type>__<username>.<ext>" in body


def test_collection_script_unknown_op(client):
    r = client.get("/api/ops/does-not-exist/collection-script")
    assert r.status_code == 404


def test_collection_script_no_op_specific_data(client):
    """The served script is byte-identical for every op (Architecture Rule #21)."""
    op_a = _create_op(client, "OpA")
    op_b = _create_op(client, "OpB")
    body_a = client.get(f"/api/ops/{op_a}/collection-script").content
    body_b = client.get(f"/api/ops/{op_b}/collection-script").content
    assert body_a == body_b


# ─── POST /import-archive — happy paths ──────────────────────────────────────

def test_import_archive_happy_path(client):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    auth_keys = (FIXTURES / "authorized_keys").read_bytes()
    auth_log = (FIXTURES / "auth.log").read_bytes()

    tarball = _build_tarball({
        "authorized_keys__bob.txt": auth_keys,
        "auth_log__.txt": auth_log,
    })

    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("test.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["files_processed"] == 2
    assert data["files_skipped"] == 0
    assert data["totals"]["new_credentials"] >= 1  # at least one key in authorized_keys
    # Records landed in the DB
    r2 = client.get(f"/api/ops/{op_id}/credentials")
    assert len(r2.json()) >= 1


def test_import_archive_idempotent(client):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    # Use id_rsa.pub as the authorized_keys content — it's a single, valid,
    # fingerprint-able key. The mixed authorized_keys fixture contains some
    # malformed keys that get a fresh Credential on every import (no fp to
    # dedup by), which would legitimately bump new_credentials on re-import.
    pub_line = (FIXTURES / "id_rsa.pub").read_bytes()
    tarball = _build_tarball({"authorized_keys__bob.txt": pub_line})

    r1 = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("test.tar.gz", tarball, "application/gzip")},
    )
    assert r1.status_code == 200
    assert r1.json()["totals"]["new_credentials"] == 1
    assert r1.json()["totals"]["new_credential_links"] == 1

    # Rebuild and re-import
    tarball2 = _build_tarball({"authorized_keys__bob.txt": pub_line})
    r2 = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("test.tar.gz", tarball2, "application/gzip")},
    )
    assert r2.status_code == 200
    assert r2.json()["totals"]["new_credentials"] == 0
    assert r2.json()["totals"]["new_credential_links"] == 0


def test_import_archive_missing_manifest_tolerated(client):
    """Filename convention is authoritative — manifest.json is optional."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    auth_keys = (FIXTURES / "authorized_keys").read_bytes()

    tarball = _build_tarball(
        {"authorized_keys__root.txt": auth_keys},
        include_manifest=False,
    )
    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("test.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 200
    assert r.json()["files_processed"] == 1


def test_import_archive_unknown_file_type_warning(client):
    """Files whose file_type is not (yet) registered produce warnings, not failures."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    tarball = _build_tarball({"iptables__.bin": b"\x00" * 32})
    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("test.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["files_processed"] == 0
    assert data["files_skipped"] == 1
    entry = data["per_file"][0]
    assert entry["filename"] == "iptables__.bin"
    assert entry["ok"] is False
    assert any("Unsupported file type" in w for w in entry["summary"]["warnings"])


def test_import_archive_err_sibling_surfaces_warning(client):
    """A <base>.err sibling in the archive is surfaced on the main file's entry."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    auth_keys = (FIXTURES / "authorized_keys").read_bytes()

    tarball = _build_tarball({
        "authorized_keys__root.txt": auth_keys,
        "authorized_keys__root.txt.err": b"Permission denied reading /root/.ssh/authorized_keys\n",
    })
    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("test.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 200
    data = r.json()
    target = next(e for e in data["per_file"] if e["filename"] == "authorized_keys__root.txt")
    assert any("Permission denied" in w for w in target["summary"]["warnings"])


def test_import_archive_filename_without_convention_skipped(client):
    """A file not matching <file_type>__<username>.<ext> is skipped with a warning."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    tarball = _build_tarball({"random_file.txt": b"garbage"})
    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("test.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["files_skipped"] == 1
    entry = data["per_file"][0]
    assert entry["ok"] is False
    assert any("does not match" in w for w in entry["summary"]["warnings"])


# ─── POST /import-archive — safety / error paths ─────────────────────────────

def test_import_archive_path_traversal_rejected(client):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    info = tarfile.TarInfo(name="../escape.txt")
    info.type = tarfile.REGTYPE
    tarball = _build_raw_tarball([info], {"../escape.txt": b"evil"})

    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("bad.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 400
    assert "parent-traversal" in r.json()["detail"]


def test_import_archive_absolute_path_rejected(client):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    info = tarfile.TarInfo(name="/etc/passwd")
    info.type = tarfile.REGTYPE
    tarball = _build_raw_tarball([info], {"/etc/passwd": b"evil"})

    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("bad.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 400
    assert "absolute path" in r.json()["detail"]


def test_import_archive_symlink_rejected(client):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    info = tarfile.TarInfo(name="innocent.txt")
    info.type = tarfile.SYMTYPE
    info.linkname = "/etc/passwd"
    tarball = _build_raw_tarball([info], {})

    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("bad.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 400
    assert "symlink/hardlink" in r.json()["detail"]


def test_import_archive_corrupt_tarball(client):
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("bad.tar.gz", b"not a real tarball", "application/gzip")},
    )
    assert r.status_code == 400
    assert "Invalid tarball" in r.json()["detail"]


def test_import_archive_oversized_rejected(client, monkeypatch):
    monkeypatch.setattr("config.settings.archive_import_max_bytes", 1024)
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    # 2 KB of gz-compressible junk — the raw body is what's checked, and we
    # need the uploaded bytes to exceed 1024 bytes.
    big_body = b"x" * 2048
    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("big.tar.gz", big_body, "application/gzip")},
    )
    assert r.status_code == 413


def test_import_archive_uncompressed_cap_boundary(client, monkeypatch):
    """Exactly-at-cap is allowed; one-byte-over is rejected. Single-file case."""
    # 512-byte file is exactly at cap → must pass
    monkeypatch.setattr("config.settings.archive_import_max_uncompressed_bytes", 512)
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    tarball = _build_tarball(
        {"etc_hosts__.txt": b"x" * 512},
        include_manifest=False,
    )
    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("t.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 200, r.text


def test_import_archive_uncompressed_cap_sums_across_members(client, monkeypatch):
    """Individual members under cap but sum trips it → rejected."""
    monkeypatch.setattr("config.settings.archive_import_max_uncompressed_bytes", 1024)
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    # Three 512-byte members → total 1536, exceeds 1024
    tarball = _build_tarball(
        {
            "etc_hosts__.txt": b"a" * 512,
            "auth_log__.txt": b"b" * 512,
            "passwd__.txt": b"c" * 512,
        },
        include_manifest=False,
    )
    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("t.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 413
    assert "uncompressed" in r.json()["detail"].lower()


def test_import_archive_gzip_bomb_rejected(client, monkeypatch):
    """A tarball whose compressed size fits under the limit but whose
    uncompressed members would blow past the uncompressed cap must be
    rejected before extractall() runs (otherwise a ~200 KB tarball can
    expand to 200+ MB of null bytes)."""
    monkeypatch.setattr("config.settings.archive_import_max_uncompressed_bytes", 1024)
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    # 4 KB of highly compressible null bytes — tarball ends up tiny but
    # the member's size field is 4096 > 1024 cap.
    payload = b"\x00" * 4096
    tarball = _build_tarball(
        {"auth_log__.txt": payload},
        include_manifest=False,
    )

    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("bomb.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 413
    assert "uncompressed" in r.json()["detail"].lower()


def test_import_archive_host_in_wrong_op_returns_404(client):
    op_a = _create_op(client, "OpA")
    op_b = _create_op(client, "OpB")
    host_in_b = _create_host(client, op_b)

    tarball = _build_tarball({"etc_hosts__.txt": b"127.0.0.1 localhost\n"})
    r = client.post(
        f"/api/ops/{op_a}/hosts/{host_in_b}/import-archive",
        files={"file": ("a.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 404


def test_import_archive_unknown_op_returns_404(client):
    # Create real host, but target an op that doesn't exist
    r = client.post(
        "/api/ops/nonexistent/hosts/also-nonexistent/import-archive",
        files={"file": ("a.tar.gz", b"", "application/gzip")},
    )
    assert r.status_code == 404


# ─── Activity log + pivot ────────────────────────────────────────────────────

def test_import_archive_alias_same_host_no_warning(client):
    """Re-importing an /etc/hosts line whose alias already points to the
    SAME host (idempotent round-trip) must NOT produce a conflict warning."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    # Seed with 10.0.0.7 + alias realbox
    seed = b"10.0.0.7 realbox\n"
    r0 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "etc_hosts", "host_id": host_id},
        files={"file": ("etc_hosts", seed, "text/plain")},
    )
    assert r0.status_code == 200
    # Re-upload the identical line via archive
    tarball = _build_tarball({"etc_hosts__.txt": seed})
    r1 = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("t.tar.gz", tarball, "application/gzip")},
    )
    assert r1.status_code == 200
    entry = next(e for e in r1.json()["per_file"] if e["filename"] == "etc_hosts__.txt")
    assert not any("already bound to another host" in w for w in entry["summary"]["warnings"]), \
        f"unexpected alias-conflict warning: {entry['summary']['warnings']}"


def test_import_archive_alias_conflict_surfaces_warning(client):
    """When an /etc/hosts line's hostname already belongs to a DIFFERENT
    *non-unresolved* host (one with operator content), the pipeline skips
    the add and surfaces it as a manual merge candidate — Phase 15 only
    auto-merges placeholder hosts."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    # First upload: 10.0.0.1 with hostname 'realname'. The auto-created
    # placeholder for 10.0.0.1 / realname starts unresolved.
    first = b"10.0.0.1 realname\n"
    r1 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "etc_hosts", "host_id": host_id},
        files={"file": ("etc_hosts", first, "text/plain")},
    )
    assert r1.status_code == 200
    # Find the placeholder and attach a HostUser so it stops being unresolved
    # (Phase 15 would otherwise auto-merge it on the next conflict).
    hosts = client.get(f"/api/ops/{op_id}/hosts").json()
    placeholder_id = next(h["id"] for h in hosts if h["nickname"] == "10.0.0.1")
    r_user = client.post(f"/api/hosts/{placeholder_id}/users", json={"username": "root"})
    assert r_user.status_code in (200, 201)

    # Second upload via archive: 10.0.0.99 claims 'realname' as an alias.
    conflicting = b"10.0.0.99 realname\n"
    tarball = _build_tarball({"etc_hosts__.txt": conflicting})
    r2 = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("t.tar.gz", tarball, "application/gzip")},
    )
    assert r2.status_code == 200
    entry = next(e for e in r2.json()["per_file"] if e["filename"] == "etc_hosts__.txt")
    assert any("already bound to another host" in w for w in entry["summary"]["warnings"]), \
        entry["summary"]["warnings"]
    assert entry["summary"]["merge_candidates"] == [
        {"alias": "realname", "conflicting_host_id": placeholder_id},
    ]


def test_import_archive_alias_conflict_auto_merges_unresolved(client):
    """When the conflicting host is an unresolved placeholder, the alias
    triggers a silent auto-merge (Phase 15) instead of a manual candidate."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    # Seed: an evidence-only placeholder for 10.0.0.1 with alias 'realname'.
    seed = b"10.0.0.1 realname\n"
    r1 = client.post(
        f"/api/ops/{op_id}/upload",
        data={"file_type": "etc_hosts", "host_id": host_id},
        files={"file": ("etc_hosts", seed, "text/plain")},
    )
    assert r1.status_code == 200
    hosts_before = client.get(f"/api/ops/{op_id}/hosts").json()
    placeholder_id = next(h["id"] for h in hosts_before if h["nickname"] == "10.0.0.1")

    # Now archive-import a conflicting line — placeholder should be merged
    # into the new 10.0.0.99 host without prompting.
    conflicting = b"10.0.0.99 realname\n"
    tarball = _build_tarball({"etc_hosts__.txt": conflicting})
    r2 = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("t.tar.gz", tarball, "application/gzip")},
    )
    assert r2.status_code == 200
    entry = next(e for e in r2.json()["per_file"] if e["filename"] == "etc_hosts__.txt")
    assert entry["summary"]["merge_candidates"] == []
    assert any("Auto-merged unresolved" in w for w in entry["summary"]["warnings"]), \
        entry["summary"]["warnings"]

    # Placeholder host is gone; the new host owns both addresses.
    hosts_after = client.get(f"/api/ops/{op_id}/hosts").json()
    assert all(h["id"] != placeholder_id for h in hosts_after)
    new_host = next(h for h in hosts_after if h["nickname"] == "10.0.0.99")
    addrs = sorted(ip["ip_address"] for ip in new_host["ips"])
    assert addrs == ["10.0.0.1", "10.0.0.99", "realname"]

    # Activity log captures the auto-merge.
    log = client.get(f"/api/ops/{op_id}/activity").json()
    auto_entries = [e for e in log if e["action"] == "host.auto_merge"]
    assert len(auto_entries) == 1
    assert "Auto-merged '10.0.0.1' into '10.0.0.99'" in auto_entries[0]["detail"]


def test_import_archive_aggregates_sudo_rules(client):
    """A sudoers file in the archive must report its sudo rules in per_file
    summary, totals, and the activity-log detail line."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    sudoers = (FIXTURES / "sudoers").read_bytes()

    tarball = _build_tarball({"sudoers__.txt": sudoers})
    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("t.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 200
    data = r.json()
    entry = next(e for e in data["per_file"] if e["filename"] == "sudoers__.txt")
    assert entry["ok"] is True
    assert entry["summary"]["new_sudo_rules"] >= 1
    assert data["totals"]["new_sudo_rules"] == entry["summary"]["new_sudo_rules"]
    # Activity log should name sudo rules
    log = client.get(f"/api/ops/{op_id}/activity").json()
    detail = next(e["detail"] for e in log if e["action"] == "upload.archive_import")
    assert "sudo rules" in detail


def test_import_archive_single_activity_log_entry(client):
    """A multi-file archive emits exactly one archive-level activity row."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)
    auth_keys = (FIXTURES / "authorized_keys").read_bytes()
    passwd = (FIXTURES / "passwd").read_bytes()
    auth_log = (FIXTURES / "auth.log").read_bytes()

    tarball = _build_tarball({
        "authorized_keys__bob.txt": auth_keys,
        "passwd__.txt": passwd,
        "auth_log__.txt": auth_log,
    })
    r = client.post(
        f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
        files={"file": ("t.tar.gz", tarball, "application/gzip")},
    )
    assert r.status_code == 200

    log = client.get(f"/api/ops/{op_id}/activity").json()
    archive_rows = [e for e in log if e["action"] == "upload.archive_import"]
    assert len(archive_rows) == 1
    assert "3 files" in archive_rows[0]["detail"]


def test_import_archive_pivot_across_hosts(client):
    """
    Seed host A's private-key side via the single-file upload, then import
    an archive with the matching authorized_keys on host B. The pivot is
    surfaced on the *second* operation — the one whose newly-seen
    fingerprint completes the pair (this mirrors test_pivot_detection in
    the single-file upload tests).
    """
    op_id = _create_op(client)
    host_a = _create_host(client, op_id, "hostA")
    host_b = _create_host(client, op_id, "hostB")

    # Step 1: seed host A with the private key
    private_key = (FIXTURES / "id_rsa").read_bytes()
    r0 = client.post(
        f"/api/ops/{op_id}/upload",
        files={"file": ("id_rsa", private_key, "text/plain")},
        data={"file_type": "private_key", "host_id": host_a, "username": "bob"},
    )
    assert r0.status_code == 200

    # Step 2: archive import of the matching public key as authorized_keys on host B
    pub_line = (FIXTURES / "id_rsa.pub").read_bytes()
    tarball = _build_tarball({"authorized_keys__root.txt": pub_line})
    r1 = client.post(
        f"/api/ops/{op_id}/hosts/{host_b}/import-archive",
        files={"file": ("t.tar.gz", tarball, "application/gzip")},
    )
    assert r1.status_code == 200
    pivots = r1.json()["pivot_opportunities"]
    assert any("hostA" in p and "hostB" in p for p in pivots), pivots
