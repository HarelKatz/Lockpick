"""Unit tests for the ip_route parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.ip_route import IpRouteParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ip_route"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="ip_route")


def test_extracts_default_and_explicit_gateways():
    """`via X` lines produce a HostData per unique gateway."""
    content = (FIXTURES / "ip_route.out").read_bytes()
    result = IpRouteParser().parse(content, _meta())

    # Two distinct `via` gateways: 10.0.0.1 and 192.168.1.1
    assert len(result.hosts_found) == 2
    addrs = {h.ip_address for h in result.hosts_found}
    assert addrs == {"10.0.0.1", "192.168.1.1"}


def test_no_connection_records():
    """Gateway is host inventory, not a connection."""
    content = (FIXTURES / "ip_route.out").read_bytes()
    result = IpRouteParser().parse(content, _meta())
    assert result.connections_found == []


def test_dedupes_repeated_gateway():
    content = (
        b"default via 10.0.0.1 dev eth0\n"
        b"192.168.1.0/24 via 10.0.0.1 dev eth0\n"
    )
    result = IpRouteParser().parse(content, _meta())
    assert len(result.hosts_found) == 1
    assert result.hosts_found[0].ip_address == "10.0.0.1"


def test_route_n_with_UG_flag():
    content = (
        b"Kernel IP routing table\n"
        b"Destination     Gateway         Genmask         Flags Metric Ref    Use Iface\n"
        b"0.0.0.0         10.0.0.1        0.0.0.0         UG    100    0        0 eth0\n"
        b"10.0.0.0        0.0.0.0         255.255.255.0   U     0      0        0 eth0\n"
    )
    result = IpRouteParser().parse(content, _meta())
    assert len(result.hosts_found) == 1
    assert result.hosts_found[0].ip_address == "10.0.0.1"


def test_stats_count():
    content = (FIXTURES / "ip_route.out").read_bytes()
    result = IpRouteParser().parse(content, _meta())
    assert result.stats == {"gateways": 2}


def test_empty_file():
    result = IpRouteParser().parse(b"", _meta())
    assert result.hosts_found == []
    assert result.stats == {"gateways": 0}
