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
    """Each non-loopback line produces ONE HostData (primary IP) with the
    line's hostnames as aliases — NOT separate HostData per identifier."""
    result = EtcHostsParser().parse(_load_fixture(), _meta())
    # 4 lines → 4 HostData (fixture has 4 non-loopback lines)
    assert len(result.hosts_found) == 4
    by_ip = {h.ip_address: h for h in result.hosts_found}
    assert set(by_ip.keys()) == {"10.0.0.1", "10.0.0.10", "192.168.1.50", "172.16.5.20"}
    # Each line carries its hostnames as aliases
    total_aliases = sum(len(h.aliases) for h in result.hosts_found)
    assert total_aliases == 8  # gateway.internal, gateway, webserver.internal, web01,
                               # db-primary.corp, db-primary, dev-box.internal, dev-box


def test_skips_loopback():
    content = b"127.0.0.1 localhost\n::1 ip6-localhost\n10.0.0.5 realhost\n"
    result = EtcHostsParser().parse(content, _meta())
    addresses = [h.ip_address for h in result.hosts_found]
    assert "127.0.0.1" not in addresses
    assert "::1" not in addresses
    assert "10.0.0.5" in addresses


def test_skips_multicast_and_reserved_ipv6():
    """IPv6 multicast / reserved lines must not produce phantom hosts,
    even via their hostname aliases (ip6-allnodes, ip6-mcastprefix, ...)."""
    content = (
        b"ff02::1 ip6-allnodes\n"
        b"ff00::0 ip6-mcastprefix\n"
        b"fe00::0 ip6-localnet\n"
        b"10.0.0.5 realhost\n"
    )
    result = EtcHostsParser().parse(content, _meta())
    assert len(result.hosts_found) == 1
    assert result.hosts_found[0].ip_address == "10.0.0.5"
    assert result.hosts_found[0].aliases == ["realhost"]


def test_skips_comments():
    content = b"# this is a comment\n10.0.0.1 host1\n"
    result = EtcHostsParser().parse(content, _meta())
    # ONE HostData for the one non-comment line
    assert len(result.hosts_found) == 1
    assert result.hosts_found[0].ip_address == "10.0.0.1"
    assert result.hosts_found[0].aliases == ["host1"]


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
    assert len(result.hosts_found) == 1
    hd = result.hosts_found[0]
    assert hd.ip_address == "10.0.0.1"
    assert hd.aliases == ["myhost"]  # comment and its words are stripped
