"""Tests for known_hosts parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.known_hosts import KnownHostsParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="known_hosts",
        username="bob",
        filename="known_hosts",
    )


def test_parses_plain_entries(metadata):
    content = (FIXTURES / "known_hosts").read_bytes()
    result = KnownHostsParser().parse(content, metadata)
    dst_ips = {c.dst_ip for c in result.connections_found}
    assert "10.10.10.1" in dst_ips
    assert "10.10.10.2" in dst_ips
    assert "hostname2.corp" in dst_ips


def test_port_notation_stripped(metadata):
    content = (FIXTURES / "known_hosts").read_bytes()
    result = KnownHostsParser().parse(content, metadata)
    dst_ips = {c.dst_ip for c in result.connections_found}
    assert "10.10.10.3" in dst_ips


def test_hashed_entry_warns(metadata):
    content = (FIXTURES / "known_hosts").read_bytes()
    result = KnownHostsParser().parse(content, metadata)
    assert any("hashed" in w.lower() for w in result.warnings)


def test_all_connections_from_upload_host(metadata):
    content = (FIXTURES / "known_hosts").read_bytes()
    result = KnownHostsParser().parse(content, metadata)
    assert all(c.src_ip == "__upload_host__" for c in result.connections_found)
    assert all(c.direction_context == "from_src_logs" for c in result.connections_found)


def test_empty_file(metadata):
    result = KnownHostsParser().parse(b"", metadata)
    assert result.connections_found == []
