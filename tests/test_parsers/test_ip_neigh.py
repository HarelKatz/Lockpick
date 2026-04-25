"""Unit tests for the ip_neigh parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.ip_neigh import IpNeighParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ip_neigh"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="ip_neigh")


def test_each_neighbor_emits_one_connection():
    """Fixture has 4 neighbors → 4 ConnectionData (3 IPv4 + 1 IPv6)."""
    content = (FIXTURES / "ip_neigh.out").read_bytes()
    result = IpNeighParser().parse(content, _meta())
    assert len(result.connections_found) == 4

    dst_ips = {c.dst_ip for c in result.connections_found}
    assert "10.0.0.1" in dst_ips
    assert "10.0.0.5" in dst_ips
    assert "10.0.0.10" in dst_ips
    assert "fe80::1" in dst_ips


def test_indicator_confidence_shape():
    """Each emitted record uses connection_type=unknown and from_src_logs."""
    content = (FIXTURES / "ip_neigh.out").read_bytes()
    result = IpNeighParser().parse(content, _meta())
    for c in result.connections_found:
        assert c.connection_type == "unknown"
        assert c.direction_context == "from_src_logs"
        assert c.src_ip == "__upload_host__"
        assert c.raw_line is not None


def test_stats_count():
    content = (FIXTURES / "ip_neigh.out").read_bytes()
    result = IpNeighParser().parse(content, _meta())
    assert result.stats == {"neighbors": 4}


def test_empty_file():
    result = IpNeighParser().parse(b"", _meta())
    assert result.connections_found == []
    assert result.stats == {"neighbors": 0}


def test_skips_comments_and_garbage():
    content = b"# comment\n\nnot a valid neighbor line\n10.0.0.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
    result = IpNeighParser().parse(content, _meta())
    assert len(result.connections_found) == 1
