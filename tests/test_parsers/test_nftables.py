"""Unit tests for the nftables parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.nftables import NftablesParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "nftables"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="nftables")


def test_only_specific_hosts_emit():
    """Fixture has 4 specific-host rules:
      ip saddr 10.0.0.99 drop
      ip saddr 10.0.0.50 ... accept
      ip daddr 10.20.30.40 ... accept
      ip6 saddr 2001:db8::5 accept
    The `192.168.0.0/16` saddr is a subnet, skipped.
    """
    content = (FIXTURES / "nft_ruleset.out").read_bytes()
    result = NftablesParser().parse(content, _meta())
    assert len(result.connections_found) == 4


def test_specific_ips_seen():
    content = (FIXTURES / "nft_ruleset.out").read_bytes()
    result = NftablesParser().parse(content, _meta())
    real_ips = set()
    for c in result.connections_found:
        if c.src_ip != "__upload_host__":
            real_ips.add(c.src_ip)
        if c.dst_ip != "__upload_host__":
            real_ips.add(c.dst_ip)
    assert real_ips == {"10.0.0.99", "10.0.0.50", "10.20.30.40", "2001:db8::5"}


def test_indicator_shape():
    content = (FIXTURES / "nft_ruleset.out").read_bytes()
    result = NftablesParser().parse(content, _meta())
    for c in result.connections_found:
        assert c.connection_type == "unknown"
        assert c.direction_context == "from_src_logs"


def test_named_set_references_skipped():
    """`ip saddr @blackhole` and `ip saddr $admin` should produce nothing."""
    content = (
        b"ip saddr @blackhole drop\n"
        b"ip saddr $admin accept\n"
        b"ip saddr 10.0.0.99 drop\n"
    )
    result = NftablesParser().parse(content, _meta())
    assert len(result.connections_found) == 1


def test_empty_file():
    result = NftablesParser().parse(b"", _meta())
    assert result.connections_found == []
    assert result.stats == {"rules": 0}
