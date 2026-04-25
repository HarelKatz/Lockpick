"""Unit tests for the ss_output parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.ss_output import SsOutputParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ss_output"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="ss_output")


def test_only_established_emits():
    """Fixture has 3 ESTAB tcp rows → 3 ConnectionData; LISTEN/UNCONN skipped."""
    content = (FIXTURES / "ss_a.out").read_bytes()
    result = SsOutputParser().parse(content, _meta())
    assert len(result.connections_found) == 3


def test_dst_ip_is_peer():
    content = (FIXTURES / "ss_a.out").read_bytes()
    result = SsOutputParser().parse(content, _meta())
    dst_ips = {c.dst_ip for c in result.connections_found}
    assert dst_ips == {"10.10.10.20", "web01.corp", "2001:db8::1"}


def test_iface_qualifier_stripped():
    """`127.0.0.53%lo` LISTEN should never reach output, but if it had, the
    `%lo` qualifier should be removed by the splitter."""
    content = (
        b"Netid State    Recv-Q Send-Q       Local Address:Port      Peer Address:Port\n"
        b"tcp   ESTAB    0      0           192.168.1.1%eth0:55656             10.10.10.20%eth0:443\n"
    )
    result = SsOutputParser().parse(content, _meta())
    assert len(result.connections_found) == 1
    assert result.connections_found[0].dst_ip == "10.10.10.20"


def test_src_is_upload_host_sentinel():
    content = (FIXTURES / "ss_a.out").read_bytes()
    result = SsOutputParser().parse(content, _meta())
    for c in result.connections_found:
        assert c.src_ip == "__upload_host__"
        assert c.connection_type == "unknown"
        assert c.direction_context == "from_src_logs"


def test_stats_counts():
    content = (FIXTURES / "ss_a.out").read_bytes()
    result = SsOutputParser().parse(content, _meta())
    assert result.stats == {"connections": 3}


def test_empty_file():
    result = SsOutputParser().parse(b"", _meta())
    assert result.connections_found == []
    assert result.stats == {"connections": 0}
