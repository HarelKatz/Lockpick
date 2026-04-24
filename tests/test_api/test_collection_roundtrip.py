"""Roundtrip smoke test — runs the real bash collection script and imports its output.

Exercises the end-to-end script → tarball → import endpoint path. Skips
automatically on systems without `bash`, `tar`, or `gzip`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

SCRIPT_PATH = Path(__file__).parent.parent.parent / "backend" / "collection_script" / "lockpick_collect.sh"


pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("tar") is None or shutil.which("gzip") is None,
    reason="bash/tar/gzip required for roundtrip test",
)


def _create_op(client, name: str = "RoundtripOp") -> str:
    r = client.post("/api/ops", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


def _create_host(client, op_id: str, nickname: str = "target") -> str:
    r = client.post(f"/api/ops/{op_id}/hosts", json={"nickname": nickname})
    assert r.status_code == 201
    return r.json()["id"]


def test_roundtrip_script_to_import(client, tmp_path):
    # Run the script with OUT_DIR pointing at tmp_path so the tarball lands there.
    result = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        env={
            "OUT_DIR": str(tmp_path),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/root"),
        },
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"script failed: stdout={result.stdout}, stderr={result.stderr}"

    tarballs = list(tmp_path.glob("lockpick_*.tar.gz"))
    assert len(tarballs) == 1, f"expected 1 tarball, got {tarballs}"
    tarball = tarballs[0]

    # Validate tarball structure
    with tarfile.open(tarball, "r:gz") as tf:
        names = [m.name for m in tf.getmembers()]
        assert any(n.endswith("manifest.json") for n in names), f"no manifest.json in {names}"
        # Extract manifest and parse it
        manifest_member = next(m for m in tf.getmembers() if m.name.endswith("manifest.json"))
        manifest_bytes = tf.extractfile(manifest_member).read()
    manifest = json.loads(manifest_bytes)
    assert "files" in manifest
    assert "hostname" in manifest
    assert "generated_at_utc" in manifest

    # POST to the import endpoint
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    with open(tarball, "rb") as f:
        r = client.post(
            f"/api/ops/{op_id}/hosts/{host_id}/import-archive",
            files={"file": ("collected.tar.gz", f.read(), "application/gzip")},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    # We cannot assert specific counters (machine-dependent content), but we
    # can assert the pipeline produced *some* result — either a processed
    # file or a skip with warnings. A manifest with no files at all would
    # indicate a script regression.
    assert data["files_processed"] + data["files_skipped"] >= 1
