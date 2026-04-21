"""Unit tests for the /etc/hosts parser."""
import os

import pytest

from parsers.etc_hosts import EtcHostsParser
from parsers import UploadMetadata

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "etc_hosts")


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="etc_hosts")


def _load_fixture() -> bytes:
    with open(FIXTURE, "rb") as f:
        return f.read()


def test_parses_ips_and_hostnames():
    result = EtcHostsParser().parse(_load_fixture(), _meta())
    addresses = [h.ip_address for h in result.hosts_found]
    # 4 IPs (10.0.0.1, 10.0.0.10, 192.168.1.50, 172.16.5.20)
    ips = [a for a in addresses if a[0].isdigit()]
    assert len(ips) == 4
    # Hostnames: gateway.internal, gateway, webserver.internal, web01,
    #            db-primary.corp, db-primary, dev-box.internal, dev-box = 8
    hostnames = [a for a in addresses if not a[0].isdigit() and ":" not in a]
    assert len(hostnames) == 8


def test_skips_loopback():
    content = b"127.0.0.1 localhost\n::1 ip6-localhost\n10.0.0.5 realhost\n"
    result = EtcHostsParser().parse(content, _meta())
    addresses = [h.ip_address for h in result.hosts_found]
    assert "127.0.0.1" not in addresses
    assert "::1" not in addresses
    assert "10.0.0.5" in addresses


def test_skips_comments():
    content = b"# this is a comment\n10.0.0.1 host1\n"
    result = EtcHostsParser().parse(content, _meta())
    assert len(result.hosts_found) == 2  # IP + hostname
    addresses = [h.ip_address for h in result.hosts_found]
    assert "10.0.0.1" in addresses
    assert "host1" in addresses


def test_skips_broadcast():
    content = b"255.255.255.255 broadcasthost\n0.0.0.0 blackhole\n10.0.0.1 real\n"
    result = EtcHostsParser().parse(content, _meta())
    addresses = [h.ip_address for h in result.hosts_found]
    assert "255.255.255.255" not in addresses
    assert "0.0.0.0" not in addresses
    assert "10.0.0.1" in addresses


def test_empty_file():
    result = EtcHostsParser().parse(b"", _meta())
    assert result.hosts_found == []
    assert result.warnings == []
    assert result.stats == {"ips": 0, "hostnames": 0}


def test_stats_counts():
    content = b"10.0.0.1 host-a host-b\n192.168.1.1 host-c\n"
    result = EtcHostsParser().parse(content, _meta())
    assert result.stats["ips"] == 2
    assert result.stats["hostnames"] == 3


def test_inline_comment_stripped():
    content = b"10.0.0.1 myhost  # this is inline\n"
    result = EtcHostsParser().parse(content, _meta())
    addresses = [h.ip_address for h in result.hosts_found]
    assert "myhost" in addresses
    assert "this" not in addresses
    assert "is" not in addresses
