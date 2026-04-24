"""
API-level test: uploading every bad/corrupt file to every supported parser type
must never return HTTP 500 — the API must return 200 with ok=true or ok=false,
but never crash.

Requires tests/fixtures/bad/ to exist.
Run `uv run --project backend tests/generate_fixtures.py` first if needed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

BAD = Path(__file__).parent.parent / "fixtures" / "bad"

pytestmark = pytest.mark.skipif(
    not BAD.exists(),
    reason="Bad fixtures not generated — run tests/generate_fixtures.py first",
)

BAD_FILES = list(BAD.iterdir()) if BAD.exists() else []

FILE_TYPES = [
    "auth_log",
    "authorized_keys",
    "bash_history",
    "etc_hosts",     # Priority 11 addition
    "known_hosts",
    "nmap_xml",      # Priority 11 addition
    "passwd",
    "private_key",
    "shadow",        # Priority 11 addition
    "ssh_config",
    "sshd_config",   # Priority 11 addition
    "sudoers",       # Priority 11 addition
    "wtmp",
]


def _create_op(client) -> str:
    r = client.post("/api/ops", json={"name": "BadFileOp"})
    assert r.status_code == 201
    return r.json()["id"]


def _create_host(client, op_id: str) -> str:
    r = client.post(f"/api/ops/{op_id}/hosts", json={"nickname": "testhost"})
    assert r.status_code == 201
    return r.json()["id"]


# Priority 22: The `op_host` module-scoped fixture below was declared but never
# passed to any test function — it was dead code. Removed here.


@pytest.mark.parametrize("bad_file", BAD_FILES, ids=[f.name for f in BAD_FILES])
@pytest.mark.parametrize("file_type", FILE_TYPES)
def test_bad_file_never_500(client, bad_file, file_type):
    """Upload must return 200, never 500, for any bad input."""
    op_id = _create_op(client)
    host_id = _create_host(client, op_id)

    content = bad_file.read_bytes()
    data = {
        "file_type": file_type,
        "host_id": host_id,
        "username": "testuser",
    }
    resp = client.post(
        f"/api/ops/{op_id}/upload",
        data=data,
        files={"file": (bad_file.name, content, "application/octet-stream")},
    )
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code} for "
        f"file_type={file_type}, file={bad_file.name}: {resp.text}"
    )
    body = resp.json()
    assert "ok" in body, f"Response missing 'ok' field: {body}"
