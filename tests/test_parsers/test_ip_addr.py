"""Unit tests for the ip_addr / ifconfig parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.ip_addr import IpAddrParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ip_addr"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="ip_addr")


def test_parses_routable_addresses_into_one_host():
    """Multiple inet/inet6 lines collapse into ONE HostData per Rule #6 / multi-id."""
    content = (FIXTURES / "ifconfig.out").read_bytes()
    result = IpAddrParser().parse(content, _meta())

    # Exactly one HostData
    assert len(result.hosts_found) == 1
    h = result.hosts_found[0]
    # Primary is the first non-loopback IPv4
    assert h.ip_address == "10.0.0.42"
    # Aliases hold the second IPv4 + the global IPv6
    assert "192.168.1.10" in h.aliases
    assert "2001:db8::42" in h.aliases


def test_loopback_and_link_local_skipped():
    content = (FIXTURES / "ifconfig.out").read_bytes()
    result = IpAddrParser().parse(content, _meta())
    h = result.hosts_found[0]
    all_addrs = {h.ip_address, *h.aliases}
    assert "127.0.0.1" not in all_addrs
    assert "::1" not in all_addrs
    # fe80:: link-local IPv6 also dropped
    assert not any(a.startswith("fe80::") for a in all_addrs)


def test_stats_counts():
    content = (FIXTURES / "ifconfig.out").read_bytes()
    result = IpAddrParser().parse(content, _meta())
    assert result.stats == {"hosts": 1, "ipv4": 2, "ipv6": 1}


def test_empty_file():
    result = IpAddrParser().parse(b"", _meta())
    assert result.hosts_found == []
    assert result.stats == {"hosts": 0, "ipv4": 0, "ipv6": 0}


def test_only_loopback_emits_nothing():
    content = (
        b"lo: flags=73<UP,LOOPBACK,RUNNING>  mtu 65536\n"
        b"        inet 127.0.0.1  netmask 255.0.0.0\n"
        b"        inet6 ::1  prefixlen 128  scopeid 0x10<host>\n"
    )
    result = IpAddrParser().parse(content, _meta())
    assert result.hosts_found == []


def test_does_not_crash_on_garbage():
    result = IpAddrParser().parse(b"\x00\x01\x02 some random binary garbage", _meta())
    # Should not raise
    assert result.hosts_found == []
