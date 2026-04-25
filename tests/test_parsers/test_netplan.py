"""Tests for netplan YAML parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.netplan import NetplanParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "netplan"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="netplan",
        filename="01-netcfg.yaml",
    )


def test_addresses_from_all_iface_sections(metadata):
    content = (FIXTURES / "typical.yaml").read_bytes()
    result = NetplanParser().parse(content, metadata)
    # 3 addresses: 192.168.1.10, 10.0.0.5, 10.10.10.5
    assert len(result.hosts_found) == 1
    h = result.hosts_found[0]
    assert h.ip_address == "192.168.1.10"
    assert sorted(h.aliases) == ["10.0.0.5", "10.10.10.5"]


def test_no_connections_emitted(metadata):
    content = (FIXTURES / "typical.yaml").read_bytes()
    result = NetplanParser().parse(content, metadata)
    assert result.connections_found == []


def test_gateway_not_emitted_as_host(metadata):
    content = (FIXTURES / "typical.yaml").read_bytes()
    result = NetplanParser().parse(content, metadata)
    h = result.hosts_found[0]
    assert "192.168.1.1" not in h.aliases
    assert h.ip_address != "192.168.1.1"


def test_stats_populated(metadata):
    content = (FIXTURES / "typical.yaml").read_bytes()
    result = NetplanParser().parse(content, metadata)
    assert result.stats["addresses"] == 3
    # gateway4 + routes[0].via both = 192.168.1.1, both counted
    assert result.stats["gateways"] == 2


def test_dhcp_only(metadata):
    content = b"""network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
"""
    result = NetplanParser().parse(content, metadata)
    assert result.hosts_found == []


def test_invalid_yaml_warns(metadata):
    content = b"network: [invalid yaml: this is not okay"
    result = NetplanParser().parse(content, metadata)
    assert any("YAML" in w or "parse" in w.lower() for w in result.warnings)


def test_empty_file(metadata):
    result = NetplanParser().parse(b"", metadata)
    assert result.hosts_found == []
