"""Tests for last_output (text) parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.last_output import LastOutputParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "last_output"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="last_output",
        filename="last.txt",
    )


def test_remote_sessions_emitted(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastOutputParser().parse(content, metadata)
    # 3 remote sessions in fixture: 10.0.0.5 / jumpbox.corp / 192.168.1.42
    assert len(result.connections_found) == 3


def test_users_correct(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastOutputParser().parse(content, metadata)
    users = sorted(c.dst_user for c in result.connections_found)
    assert users == ["alice", "bob", "root"]


def test_src_ips_correct(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastOutputParser().parse(content, metadata)
    src_ips = sorted(c.src_ip for c in result.connections_found)
    assert src_ips == ["10.0.0.5", "192.168.1.42", "jumpbox.corp"]


def test_reboot_shutdown_skipped(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastOutputParser().parse(content, metadata)
    assert not any(c.dst_user in {"reboot", "shutdown"} for c in result.connections_found)


def test_local_tty_session_skipped(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastOutputParser().parse(content, metadata)
    # kbrazil's ttyS0 line had no host column — must not be emitted
    assert not any(c.dst_user == "kbrazil" for c in result.connections_found)


def test_dst_is_upload_host(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastOutputParser().parse(content, metadata)
    assert all(c.dst_ip == "__upload_host__" for c in result.connections_found)
    assert all(c.direction_context == "from_dst_logs" for c in result.connections_found)


def test_footer_skipped(metadata):
    content = b"wtmp begins Tue Jan  5 00:08:28 2021\n"
    result = LastOutputParser().parse(content, metadata)
    assert result.connections_found == []


def test_empty_file(metadata):
    result = LastOutputParser().parse(b"", metadata)
    assert result.connections_found == []


def test_stats_populated(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastOutputParser().parse(content, metadata)
    assert result.stats["records_parsed"] == 3
