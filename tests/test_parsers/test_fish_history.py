"""Tests for fish_history parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.fish_history import FishHistoryParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "fish_history"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="fish_history",
        username="alice",
        filename="fish_history",
    )


def test_parses_ssh_commands(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = FishHistoryParser().parse(content, metadata)
    # 4 ssh-family commands in the fixture
    assert len(result.connections_found) == 4


def test_dst_ips_correct(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = FishHistoryParser().parse(content, metadata)
    dsts = sorted(c.dst_ip for c in result.connections_found)
    assert dsts == ["10.0.0.5", "archive.example.com", "backup.example.com", "jumpbox.corp"]


def test_users_extracted(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = FishHistoryParser().parse(content, metadata)
    by_dst = {c.dst_ip: c.dst_user for c in result.connections_found}
    assert by_dst["10.0.0.5"] == "root"
    assert by_dst["jumpbox.corp"] == "ops"


def test_timestamps_extracted(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = FishHistoryParser().parse(content, metadata)
    assert all(c.timestamp is not None for c in result.connections_found)


def test_connection_types_classified(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = FishHistoryParser().parse(content, metadata)
    types = {c.connection_type for c in result.connections_found}
    assert "ssh" in types
    assert "scp" in types
    assert "rsync" in types


def test_stats_populated(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = FishHistoryParser().parse(content, metadata)
    assert result.stats["ssh_commands"] == 4
    # 7 cmd: blocks in fixture
    assert result.stats["commands_parsed"] == 7


def test_paths_block_ignored(metadata):
    content = b"- cmd: cd /tmp\n  when: 1700000000\n  paths:\n    - /tmp/\n"
    result = FishHistoryParser().parse(content, metadata)
    assert result.connections_found == []
    assert result.stats["commands_parsed"] == 1


def test_empty_file(metadata):
    result = FishHistoryParser().parse(b"", metadata)
    assert result.connections_found == []


def test_ssh_keygen_family_not_matched(metadata):
    """ssh-keygen / ssh-add / ssh-agent / ssh-keyscan and the quoted
    `echo "running ssh tunnel"` must NOT emit ConnectionData.

    Only `sshpass -p ... ssh user@host` and the bare `ssh user@example.com`
    are real — exactly 2 connections in total.
    """
    content = (FIXTURES / "false_positives").read_bytes()
    result = FishHistoryParser().parse(content, metadata)
    assert len(result.connections_found) == 2
    dsts = sorted(c.dst_ip for c in result.connections_found)
    assert dsts == ["example.com", "host"]
    assert "tunnel" not in dsts
    assert "ed25519" not in dsts
    assert "secret" not in dsts
