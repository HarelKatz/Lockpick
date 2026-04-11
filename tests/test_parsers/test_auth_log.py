"""Tests for auth.log parser."""
import gzip
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.auth_log import AuthLogParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="auth_log",
        filename="auth.log",
    )


def test_parses_accepted_logins(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    # Fixture has exactly 2 Accepted lines and 2 Failed lines; only accepted become connections
    assert len(result.connections_found) == 2
    assert all("Accepted" in c.raw_line for c in result.connections_found)


def test_failed_logins_not_in_connections(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert not any("Failed" in c.raw_line for c in result.connections_found)



def test_fingerprint_extracted(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    fps = [c.credential_fingerprint for c in result.connections_found if c.credential_fingerprint]
    assert any("SHA256:abc123" in fp for fp in fps)


def test_all_dst_upload_host(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert all(c.dst_ip == "__upload_host__" for c in result.connections_found)
    assert all(c.direction_context == "from_dst_logs" for c in result.connections_found)


def test_stats_populated(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert result.stats["accepted_logins"] >= 2


def test_gzip_decompressed(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    gz = gzip.compress(content)
    result = AuthLogParser().parse(gz, metadata)
    assert len(result.connections_found) > 0


def test_empty_file(metadata):
    result = AuthLogParser().parse(b"", metadata)
    assert result.connections_found == []
