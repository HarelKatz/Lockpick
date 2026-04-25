"""Tests for RHEL/CentOS ifcfg-* parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.ifcfg import IfcfgParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ifcfg"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="ifcfg",
        filename="ifcfg-eth0",
    )


def test_emits_one_hostdata_with_primary_and_aliases(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = IfcfgParser().parse(content, metadata)
    assert len(result.hosts_found) == 1
    h = result.hosts_found[0]
    # IPADDR comes first in the file
    assert h.ip_address == "192.168.1.10"
    # Aliases: IPADDR2, IPADDR3, IPV6ADDR, IPV6ADDR_SECONDARIES (2 entries) = 5
    assert sorted(h.aliases) == [
        "10.0.0.5",
        "10.1.0.5",
        "2001:db8::1",
        "2001:db8::2",
        "2001:db8::3",
    ]


def test_no_connections_emitted(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = IfcfgParser().parse(content, metadata)
    assert result.connections_found == []


def test_gateway_not_emitted_as_host(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = IfcfgParser().parse(content, metadata)
    h = result.hosts_found[0]
    assert "192.168.1.1" not in h.aliases
    assert "2001:db8::ffff" not in h.aliases


def test_stats_populated(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = IfcfgParser().parse(content, metadata)
    assert result.stats["addresses"] == 6
    assert result.stats["gateways"] == 2


def test_dhcp_only_no_addresses(metadata):
    content = b"DEVICE=eth0\nBOOTPROTO=dhcp\nONBOOT=yes\n"
    result = IfcfgParser().parse(content, metadata)
    assert result.hosts_found == []


def test_quoted_values(metadata):
    content = b'IPADDR="10.0.0.5"\nGATEWAY="10.0.0.1"\n'
    result = IfcfgParser().parse(content, metadata)
    assert len(result.hosts_found) == 1
    assert result.hosts_found[0].ip_address == "10.0.0.5"


def test_empty_file(metadata):
    result = IfcfgParser().parse(b"", metadata)
    assert result.hosts_found == []
