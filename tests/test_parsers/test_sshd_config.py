"""Tests for SshdConfigParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.sshd_config import SshdConfigParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="sshd_config",
        filename="sshd_config",
    )


def test_allow_users_creates_host_users(metadata):
    content = (FIXTURES / "sshd_config").read_bytes()
    result = SshdConfigParser().parse(content, metadata)

    usernames = {u[0] for u in result.host_users_found}
    assert "alice" in usernames
    assert "bob" in usernames
    assert result.credentials_found == []
    assert result.connections_found == []


def test_stats_keys(metadata):
    content = (FIXTURES / "sshd_config").read_bytes()
    result = SshdConfigParser().parse(content, metadata)

    assert result.stats.get("port") == "22"
    assert result.stats.get("permitrootlogin") == "no"
    assert result.stats.get("passwordauthentication") == "no"
    assert result.stats.get("allow_users") == ["alice", "bob"]
    assert result.stats.get("allow_groups") == ["sshusers", "admins"]
    assert result.stats.get("deny_users") == ["baduser"]


def test_match_block_stops_parsing(metadata):
    content = (FIXTURES / "sshd_config").read_bytes()
    result = SshdConfigParser().parse(content, metadata)

    # The Match block in the fixture is followed by AllowUsers internal_user —
    # that user must NOT appear in host_users_found
    usernames = {u[0] for u in result.host_users_found}
    assert "internal_user" not in usernames
    assert any("Match block" in w for w in result.warnings)


def test_user_at_host_stripped(metadata):
    content = b"AllowUsers alice@10.0.0.1 bob@192.168.1.0/24\n"
    result = SshdConfigParser().parse(content, metadata)

    usernames = {u[0] for u in result.host_users_found}
    assert "alice" in usernames
    assert "bob" in usernames
    assert "alice@10.0.0.1" not in usernames
    assert "bob@192.168.1.0/24" not in usernames


def test_empty_file(metadata):
    result = SshdConfigParser().parse(b"", metadata)
    assert result.host_users_found == []
    assert result.credentials_found == []
    assert result.connections_found == []
    assert result.warnings == []
    assert result.stats == {}


def test_no_allow_users(metadata):
    content = b"Port 2222\nPermitRootLogin yes\n"
    result = SshdConfigParser().parse(content, metadata)

    assert result.host_users_found == []
    assert result.stats["port"] == "2222"
    assert result.stats["permitrootlogin"] == "yes"
    assert "allow_users" not in result.stats


def test_keys_are_case_insensitive(metadata):
    content = b"ALLOWUSERS Charlie\nPERMITROOTLOGIN yes\nPASSWORDAUTHENTICATION no\n"
    result = SshdConfigParser().parse(content, metadata)

    assert any(u[0] == "Charlie" for u in result.host_users_found)
    assert result.stats.get("permitrootlogin") == "yes"
    assert result.stats.get("passwordauthentication") == "no"


def test_comment_lines_ignored(metadata):
    content = b"# Port 9999\nPort 22\n"
    result = SshdConfigParser().parse(content, metadata)
    assert result.stats.get("port") == "22"
