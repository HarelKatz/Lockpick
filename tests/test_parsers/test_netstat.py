"""Unit tests for the netstat parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.netstat import NetstatParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "netstat"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="netstat")


def test_only_established_emits_connections():
    """Fixture has 3 ESTABLISHED tcp rows → 3 ConnectionData; LISTEN/UNIX skipped."""
    content = (FIXTURES / "netstat_an.out").read_bytes()
    result = NetstatParser().parse(content, _meta())
    assert len(result.connections_found) == 3


def test_dst_ip_is_foreign_host():
    content = (FIXTURES / "netstat_an.out").read_bytes()
    result = NetstatParser().parse(content, _meta())
    dst_ips = {c.dst_ip for c in result.connections_found}
    assert dst_ips == {"10.0.0.5", "10.10.10.20", "web01.corp"}


def test_src_is_upload_host_sentinel():
    """Local addresses are routed back to upload host via sentinel."""
    content = (FIXTURES / "netstat_an.out").read_bytes()
    result = NetstatParser().parse(content, _meta())
    for c in result.connections_found:
        assert c.src_ip == "__upload_host__"
        assert c.connection_type == "unknown"
        assert c.direction_context == "from_src_logs"


def test_unix_sockets_section_ignored():
    """Once the UNIX-domain header appears, no more emissions."""
    content = (FIXTURES / "netstat_an.out").read_bytes()
    result = NetstatParser().parse(content, _meta())
    # If UNIX section bled through, we'd have entries with "/run/systemd/notify"
    for c in result.connections_found:
        assert "/" not in c.dst_ip


def test_stats_counts():
    content = (FIXTURES / "netstat_an.out").read_bytes()
    result = NetstatParser().parse(content, _meta())
    assert result.stats == {"connections": 3}


def test_empty_file():
    result = NetstatParser().parse(b"", _meta())
    assert result.connections_found == []
    assert result.stats == {"connections": 0}
