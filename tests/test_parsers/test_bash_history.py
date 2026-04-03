"""Tests for bash_history parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.bash_history import BashHistoryParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="bash_history",
        username="alice",
        filename=".bash_history",
    )


def test_parses_ssh_commands(metadata):
    content = (FIXTURES / "bash_history").read_bytes()
    result = BashHistoryParser().parse(content, metadata)
    dst_ips = {c.dst_ip for c in result.connections_found}
    assert "10.10.1.1" in dst_ips
    assert "10.10.1.2" in dst_ips
    assert "10.10.1.3" in dst_ips


def test_scp_rsync_sftp_detected(metadata):
    content = (FIXTURES / "bash_history").read_bytes()
    result = BashHistoryParser().parse(content, metadata)
    types = {c.connection_type for c in result.connections_found}
    assert "scp" in types
    assert "rsync" in types
    assert "sftp" in types


def test_user_at_host_extracted(metadata):
    content = (FIXTURES / "bash_history").read_bytes()
    result = BashHistoryParser().parse(content, metadata)
    root_conns = [c for c in result.connections_found if c.dst_user == "root"]
    assert len(root_conns) >= 1


def test_dash_l_flag(metadata):
    content = b"ssh -l bob 10.10.9.9\n"
    result = BashHistoryParser().parse(content, metadata)
    assert len(result.connections_found) == 1
    assert result.connections_found[0].dst_user == "bob"
    assert result.connections_found[0].dst_ip == "10.10.9.9"


def test_keygen_noted_as_warning(metadata):
    content = b"ssh-keygen -t ed25519 -f ~/.ssh/key\n"
    result = BashHistoryParser().parse(content, metadata)
    assert any("keygen" in w.lower() or "ssh-keygen" in w.lower() for w in result.warnings)


def test_non_ssh_lines_ignored(metadata):
    content = b"ls -la\ncat /etc/passwd\nwhoami\n"
    result = BashHistoryParser().parse(content, metadata)
    assert result.connections_found == []


def test_empty_file(metadata):
    result = BashHistoryParser().parse(b"", metadata)
    assert result.connections_found == []
