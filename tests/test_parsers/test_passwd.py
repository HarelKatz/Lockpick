"""Tests for /etc/passwd parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.passwd import PasswdParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="passwd",
        filename="passwd",
    )


def test_parses_login_users(metadata):
    content = (FIXTURES / "passwd").read_bytes()
    result = PasswdParser().parse(content, metadata)
    usernames = {u[0] for u in result.host_users_found}
    assert "root" in usernames
    assert "alice" in usernames
    assert "bob" in usernames
    assert "svc_deploy" in usernames


def test_skips_system_users(metadata):
    content = (FIXTURES / "passwd").read_bytes()
    result = PasswdParser().parse(content, metadata)
    usernames = {u[0] for u in result.host_users_found}
    assert "daemon" not in usernames
    assert "bin" not in usernames
    assert "www-data" not in usernames
    assert "systemd-network" not in usernames


def test_shell_and_home_preserved(metadata):
    content = (FIXTURES / "passwd").read_bytes()
    result = PasswdParser().parse(content, metadata)
    alice = next((u for u in result.host_users_found if u[0] == "alice"), None)
    assert alice is not None
    assert alice[1] == "/bin/bash"
    assert alice[2] == "/home/alice"


def test_no_credentials_or_connections(metadata):
    content = (FIXTURES / "passwd").read_bytes()
    result = PasswdParser().parse(content, metadata)
    assert result.credentials_found == []
    assert result.connections_found == []


def test_stats_populated(metadata):
    content = (FIXTURES / "passwd").read_bytes()
    result = PasswdParser().parse(content, metadata)
    assert result.stats["users_parsed"] == 4


def test_malformed_line_warns(metadata):
    result = PasswdParser().parse(b"root:x:0\n", metadata)
    assert len(result.warnings) > 0


def test_empty_file(metadata):
    result = PasswdParser().parse(b"", metadata)
    assert result.host_users_found == []
