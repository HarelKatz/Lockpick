"""Tests for NmapXmlParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.nmap_xml import NmapXmlParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="nmap_xml",
        filename="nmap_scan.xml",
    )


def test_parses_up_hosts(metadata):
    content = (FIXTURES / "nmap_scan.xml").read_bytes()
    result = NmapXmlParser().parse(content, metadata)

    # 3 up hosts. One HostData per HOST (not per IP) — the dbserver's
    # second IP and any hostnames ride along as aliases on a single record.
    assert len(result.hosts_found) == 3
    assert result.credentials_found == []
    assert result.connections_found == []
    assert result.stats["hosts_found"] == 3


def test_hostname_used_as_nickname(metadata):
    content = (FIXTURES / "nmap_scan.xml").read_bytes()
    result = NmapXmlParser().parse(content, metadata)

    webserver = next(h for h in result.hosts_found if h.ip_address == "10.0.0.5")
    assert webserver.nickname == "webserver.corp.local"


def test_ip_used_as_nickname_when_no_hostname(metadata):
    content = (FIXTURES / "nmap_scan.xml").read_bytes()
    result = NmapXmlParser().parse(content, metadata)

    ip_only = next(h for h in result.hosts_found if h.ip_address == "10.0.0.10")
    assert ip_only.nickname == "10.0.0.10"


def test_skips_down_hosts(metadata):
    content = (FIXTURES / "nmap_scan.xml").read_bytes()
    result = NmapXmlParser().parse(content, metadata)

    ips = {h.ip_address for h in result.hosts_found}
    assert "10.0.0.99" not in ips


def test_dual_stack_host_emits_both_ips(metadata):
    """Dual-stack host keeps both addresses on the SAME HostData — primary
    in ip_address, secondary in aliases — so the upload pipeline creates
    one Host with two HostIPs rather than two separate Hosts."""
    content = (FIXTURES / "nmap_scan.xml").read_bytes()
    result = NmapXmlParser().parse(content, metadata)

    dual_stack = next(h for h in result.hosts_found if h.ip_address == "10.0.0.20")
    assert "fe80::1" in dual_stack.aliases


def test_empty_file(metadata):
    result = NmapXmlParser().parse(b"", metadata)
    assert result.hosts_found == []
    assert result.credentials_found == []
    assert result.connections_found == []


def test_malformed_xml(metadata):
    result = NmapXmlParser().parse(b"this is not xml <<<>><><", metadata)
    assert isinstance(result.warnings, list)
    assert len(result.warnings) > 0
    assert result.hosts_found == []


def test_host_with_no_address_skipped(metadata):
    xml = b"""<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <hostnames><hostname name="ghost.local" type="PTR"/></hostnames>
  </host>
</nmaprun>"""
    result = NmapXmlParser().parse(xml, metadata)
    assert result.hosts_found == []
    assert any("ghost.local" in w for w in result.warnings)


def test_all_down_hosts(metadata):
    xml = b"""<?xml version="1.0"?>
<nmaprun>
  <host><status state="down"/><address addr="10.0.0.1" addrtype="ipv4"/></host>
  <host><status state="down"/><address addr="10.0.0.2" addrtype="ipv4"/></host>
</nmaprun>"""
    result = NmapXmlParser().parse(xml, metadata)
    assert result.hosts_found == []
    assert result.stats["hosts_found"] == 0
