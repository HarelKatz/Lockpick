"""Tests for ShadowParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.shadow import ShadowParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="shadow",
        filename="shadow",
    )


def test_parses_valid_hashes(metadata):
    content = (FIXTURES / "shadow").read_bytes()
    result = ShadowParser().parse(content, metadata)

    # root and alice have valid hashes; bob has locked hash (still stored)
    cred_users = {c.username for c in result.credentials_found}
    assert "root" in cred_users
    assert "alice" in cred_users
    assert "bob" in cred_users  # locked but recoverable hash

    for cred in result.credentials_found:
        assert cred.cred_type == "password"
        assert cred.relationship_type == "found_on_disk"
        assert cred.name == f"shadow hash for {cred.username}"
        # Stored hash must not begin with "!" (lock prefix stripped)
        assert not cred.value.startswith("!")


def test_locked_account_with_hash(metadata):
    content = b"bob:!$6$salt$hashvalue:19800:0:99999:7:::\n"
    result = ShadowParser().parse(content, metadata)

    assert len(result.credentials_found) == 1
    assert result.credentials_found[0].username == "bob"
    assert result.credentials_found[0].value == "$6$salt$hashvalue"
    assert any("locked" in w for w in result.warnings)


def test_bare_locked_markers_no_credential(metadata):
    content = b"daemon:*:19000:0:99999:7:::\nnobody:!:19000:0:99999:7:::\n"
    result = ShadowParser().parse(content, metadata)

    # No credential and no HostUser — service accounts with bare lock markers
    assert result.credentials_found == []
    assert result.host_users_found == []
    assert any("daemon" in w for w in result.warnings)
    assert any("nobody" in w for w in result.warnings)


def test_shadowless_x(metadata):
    content = b"nologin:x:19000:0:99999:7:::\n"
    result = ShadowParser().parse(content, metadata)

    # x placeholder means password is in /etc/shadow but not here — skip HostUser
    assert result.credentials_found == []
    assert result.host_users_found == []
    assert any("x placeholder" in w or "no hash" in w for w in result.warnings)


def test_empty_password_no_credential(metadata):
    content = b"nopass::19000:0:99999:7:::\n"
    result = ShadowParser().parse(content, metadata)

    # Empty password sentinel — no HostUser created
    assert result.credentials_found == []
    assert result.host_users_found == []


def test_empty_file(metadata):
    result = ShadowParser().parse(b"", metadata)
    assert result.credentials_found == []
    assert result.host_users_found == []
    assert result.warnings == []
    assert result.stats["hashes_found"] == 0
    assert result.stats["users_found"] == 0


def test_malformed_lines(metadata):
    content = b"nocolon\nalso_bad\n"
    result = ShadowParser().parse(content, metadata)
    assert result.credentials_found == []
    assert len(result.warnings) == 2
    assert all("skipping" in w for w in result.warnings)


def test_comment_lines_ignored(metadata):
    content = b"# This is a comment\nroot:$6$salt$hash:0:0:99999:7:::\n"
    result = ShadowParser().parse(content, metadata)
    assert len(result.credentials_found) == 1
    assert result.credentials_found[0].username == "root"


def test_stats(metadata):
    content = (FIXTURES / "shadow").read_bytes()
    result = ShadowParser().parse(content, metadata)
    assert result.stats["hashes_found"] == 3  # root, alice, bob (locked but recoverable)
    assert result.stats["users_found"] == 3   # only users with actual hashes get HostUser
