"""Tests for shell rc parser (bashrc/zshrc)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.shell_rc import ShellRcParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "shell_rc"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="bashrc",
        username="alice",
        filename=".bashrc",
    )


def test_ssh_aliases_extracted(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    # 2 aliases (jb=10.0.0.5, web=web01.corp) + scp + rsync = 4 connections
    assert len(result.connections_found) == 4


def test_ssh_dsts_correct(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    dsts = sorted(c.dst_ip for c in result.connections_found)
    assert dsts == ["10.0.0.5", "archive.example.com", "backup.example.com", "web01.corp"]


def test_ssh_users_extracted(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    by_dst = {c.dst_ip: c.dst_user for c in result.connections_found}
    assert by_dst["10.0.0.5"] == "ops"
    assert by_dst["web01.corp"] == "root"
    assert by_dst["backup.example.com"] == "admin"
    assert by_dst["archive.example.com"] == "user"


def test_connection_types_classified(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    types = {c.connection_type for c in result.connections_found}
    assert "ssh" in types
    assert "scp" in types
    assert "rsync" in types


def test_secrets_harvested(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, GITHUB_TOKEN, DB_PASSWORD, DATABASE_DSN = 5
    assert len(result.credentials_found) == 5


def test_secret_names_correct(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    names = sorted(c.name for c in result.credentials_found)
    assert names == [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "DATABASE_DSN",
        "DB_PASSWORD",
        "GITHUB_TOKEN",
    ]


def test_secret_values_unquoted(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    by_name = {c.name: c.value for c in result.credentials_found}
    assert by_name["AWS_ACCESS_KEY_ID"] == "AKIAEXAMPLE12345"
    assert by_name["DB_PASSWORD"] == "hunter2"
    assert by_name["GITHUB_TOKEN"] == "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def test_dynamic_values_skipped(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    # PATH, SSH_AUTH_SOCK, EDITOR, FOO=$(hostname), PROMPT must NOT appear
    names = {c.name for c in result.credentials_found}
    assert "PATH" not in names
    assert "SSH_AUTH_SOCK" not in names
    assert "EDITOR" not in names
    assert "FOO" not in names
    assert "PROMPT" not in names


def test_secret_cred_type(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    assert all(c.cred_type == "password" for c in result.credentials_found)


def test_secret_username_from_metadata(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    assert all(c.username == "alice" for c in result.credentials_found)


def test_stats_populated(metadata):
    content = (FIXTURES / "bashrc_typical").read_bytes()
    result = ShellRcParser().parse(content, metadata)
    assert result.stats["ssh_commands"] == 4
    assert result.stats["secrets"] == 5


def test_empty_file(metadata):
    result = ShellRcParser().parse(b"", metadata)
    assert result.connections_found == []
    assert result.credentials_found == []


def test_comments_ignored(metadata):
    content = b"# export DB_PASSWORD=secret\n# ssh root@somewhere\n"
    result = ShellRcParser().parse(content, metadata)
    assert result.connections_found == []
    assert result.credentials_found == []
