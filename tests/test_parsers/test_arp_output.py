"""Unit tests for the arp parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.arp_output import ArpParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "arp"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="arp")


def test_parses_arp_an_format():
    """`arp -an` BSD-style format → 3 ConnectionData."""
    content = (FIXTURES / "arp_an.out").read_bytes()
    result = ArpParser().parse(content, _meta())
    assert len(result.connections_found) == 3
    dst_ips = {c.dst_ip for c in result.connections_found}
    assert dst_ips == {"10.0.0.1", "10.0.0.254", "192.168.1.5"}


def test_indicator_shape():
    content = (FIXTURES / "arp_an.out").read_bytes()
    result = ArpParser().parse(content, _meta())
    for c in result.connections_found:
        assert c.connection_type == "unknown"
        assert c.direction_context == "from_src_logs"
        assert c.src_ip == "__upload_host__"


def test_parses_proc_net_arp():
    """Linux `/proc/net/arp` style → header skipped, data rows parsed."""
    content = (
        b"IP address       HW type     Flags       HW address            Mask     Device\n"
        b"10.0.0.1         0x1         0x2         00:50:56:f3:2f:ae     *        eth0\n"
        b"10.0.0.5         0x1         0x2         00:50:56:f7:4a:fc     *        eth0\n"
    )
    result = ArpParser().parse(content, _meta())
    assert len(result.connections_found) == 2
    assert {c.dst_ip for c in result.connections_found} == {"10.0.0.1", "10.0.0.5"}


def test_parses_arp_columnar():
    """`arp` Linux columnar (Address/HWtype/HWaddress/Flags/Mask/Iface)."""
    content = (
        b"Address                  HWtype  HWaddress           Flags Mask            Iface\n"
        b"10.0.0.1                 ether   00:50:56:c0:00:08   C                     eth0\n"
        b"10.0.0.99                ether   00:50:56:c0:00:01   C                     eth0\n"
    )
    result = ArpParser().parse(content, _meta())
    assert len(result.connections_found) == 2


def test_empty_file():
    result = ArpParser().parse(b"", _meta())
    assert result.connections_found == []
    assert result.stats == {"neighbors": 0}
