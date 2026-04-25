"""Tests for lastlog parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.lastlog import LastlogParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "lastlog"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="lastlog",
        filename="lastlog",
    )


def test_typical_emits_only_remote_logins(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastlogParser().parse(content, metadata)
    # 5 UIDs in fixture: UID0/UID1 are remote logins, UID2/UID4 never logged in,
    # UID3 has empty ll_host (local console) — only 2 connection records emitted.
    assert len(result.connections_found) == 2


def test_emits_remote_ip_and_hostname(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastlogParser().parse(content, metadata)
    src_ips = sorted(c.src_ip for c in result.connections_found)
    assert src_ips == ["10.0.0.5", "jumpbox.example.com"]


def test_dst_is_upload_host(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastlogParser().parse(content, metadata)
    assert all(c.dst_ip == "__upload_host__" for c in result.connections_found)
    assert all(c.direction_context == "from_dst_logs" for c in result.connections_found)


def test_uid_in_dst_user(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastlogParser().parse(content, metadata)
    users = sorted(c.dst_user for c in result.connections_found)
    assert users == ["uid:0", "uid:1"]


def test_timestamps_present(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastlogParser().parse(content, metadata)
    assert all(c.timestamp is not None for c in result.connections_found)


def test_stats_populated(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = LastlogParser().parse(content, metadata)
    assert result.stats["records_parsed"] == 2
    assert result.stats["uids_with_login"] == 2


def test_empty_file(metadata):
    content = (FIXTURES / "empty").read_bytes()
    result = LastlogParser().parse(content, metadata)
    assert result.connections_found == []
    assert result.stats["records_parsed"] == 0


def test_truncated_file_warns(metadata):
    content = (FIXTURES / "truncated").read_bytes()
    result = LastlogParser().parse(content, metadata)
    assert any("not a multiple" in w for w in result.warnings)
