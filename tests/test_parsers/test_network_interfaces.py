"""Tests for /etc/network/interfaces parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.network_interfaces import NetworkInterfacesParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "network_interfaces"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="network_interfaces",
        filename="interfaces",
    )


def test_emits_one_hostdata_with_primary_and_aliases(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = NetworkInterfacesParser().parse(content, metadata)
    assert len(result.hosts_found) == 1
    h = result.hosts_found[0]
    assert h.ip_address == "192.168.1.10"
    assert h.aliases == ["10.0.0.5"]


def test_loopback_skipped(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = NetworkInterfacesParser().parse(content, metadata)
    h = result.hosts_found[0]
    assert "127.0.0.1" not in h.aliases
    assert h.ip_address != "127.0.0.1"


def test_no_connections_emitted(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = NetworkInterfacesParser().parse(content, metadata)
    assert result.connections_found == []


def test_gateway_not_emitted_as_host(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = NetworkInterfacesParser().parse(content, metadata)
    h = result.hosts_found[0]
    # 192.168.1.1 is the gateway — must NOT be in primary IP or aliases.
    assert h.ip_address != "192.168.1.1"
    assert "192.168.1.1" not in h.aliases


def test_stats_populated(metadata):
    content = (FIXTURES / "typical").read_bytes()
    result = NetworkInterfacesParser().parse(content, metadata)
    assert result.stats["addresses"] == 2
    assert result.stats["gateways"] == 1


def test_empty_file(metadata):
    result = NetworkInterfacesParser().parse(b"", metadata)
    assert result.hosts_found == []
    assert result.stats["addresses"] == 0


def test_dhcp_only_no_addresses(metadata):
    content = b"auto eth0\niface eth0 inet dhcp\n"
    result = NetworkInterfacesParser().parse(content, metadata)
    assert result.hosts_found == []
