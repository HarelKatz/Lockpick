"""Unit tests for the iptables parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.iptables import IptablesParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "iptables"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="iptables")


def test_only_specific_hosts_emit():
    """Subnets, `anywhere`, and 0.0.0.0/0 produce no output.

    Fixture has 4 rules with specific host IPs:
      DROP 10.0.0.99 → anywhere
      ACCEPT 10.0.0.50 → anywhere (ssh)
      DROP 15.15.15.51 → anywhere
      ACCEPT anywhere → 10.20.30.40 (https output)
    The `192.168.1.0/24` line is skipped (not a /32).
    """
    content = (FIXTURES / "iptables_L.out").read_bytes()
    result = IptablesParser().parse(content, _meta())
    assert len(result.connections_found) == 4


def test_src_or_dst_routed_to_upload_host_sentinel():
    """If only one side is a specific IP, the other becomes the sentinel."""
    content = (FIXTURES / "iptables_L.out").read_bytes()
    result = IptablesParser().parse(content, _meta())
    for c in result.connections_found:
        assert c.connection_type == "unknown"
        # Exactly one side should be a real IP
        assert c.src_ip == "__upload_host__" or c.dst_ip == "__upload_host__"


def test_specific_ips_seen():
    content = (FIXTURES / "iptables_L.out").read_bytes()
    result = IptablesParser().parse(content, _meta())
    # Collect all real IPs from either src or dst
    real_ips = set()
    for c in result.connections_found:
        if c.src_ip != "__upload_host__":
            real_ips.add(c.src_ip)
        if c.dst_ip != "__upload_host__":
            real_ips.add(c.dst_ip)
    assert real_ips == {"10.0.0.99", "10.0.0.50", "15.15.15.51", "10.20.30.40"}


def test_iptables_save_format():
    """`-A INPUT -s 10.0.0.5/32` style is also parsed."""
    content = (
        b"-A INPUT -s 10.0.0.5/32 -p tcp -j ACCEPT\n"
        b"-A INPUT -d 10.20.30.40/32 -p tcp -j DROP\n"
        b"-A INPUT -s 192.168.0.0/24 -p tcp -j ACCEPT\n"
    )
    result = IptablesParser().parse(content, _meta())
    assert len(result.connections_found) == 2


def test_dedup_repeated_rules():
    content = (
        b"Chain INPUT (policy ACCEPT)\n"
        b"target     prot opt source               destination\n"
        b"DROP       all  --  10.0.0.99            anywhere\n"
        b"DROP       all  --  10.0.0.99            anywhere\n"
        b"DROP       all  --  10.0.0.99            anywhere\n"
    )
    result = IptablesParser().parse(content, _meta())
    assert len(result.connections_found) == 1


def test_empty_file():
    result = IptablesParser().parse(b"", _meta())
    assert result.connections_found == []
    assert result.stats == {"rules": 0}
