"""Tests for wtmp parser."""
import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.wtmp import WtmpParser, _UTMP_FMT, _UTMP_SIZE, UT_USER_PROCESS


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="wtmp",
        filename="wtmp",
    )


def _make_utmp_record(user: str, host: str, ts: int, ut_type: int = UT_USER_PROCESS) -> bytes:
    """Build a minimal utmp record."""
    return struct.pack(
        _UTMP_FMT,
        ut_type,         # ut_type
        1234,            # ut_pid
        b"pts/0",        # ut_line
        b"s/0",          # ut_id
        user.encode().ljust(32, b"\x00"),   # ut_user
        host.encode().ljust(256, b"\x00"),  # ut_host
        b"\x00" * 4,     # ut_exit
        0,               # ut_session
        ts,              # tv_sec
        0,               # tv_usec
        0, 0, 0, 0,      # addr_v6
        b"\x00" * 20,    # __unused
    )


def test_parses_valid_records(metadata):
    data = (
        _make_utmp_record("root", "10.10.0.5", 1710507720)
        + _make_utmp_record("alice", "10.10.0.9", 1710507800)
    )
    result = WtmpParser().parse(data, metadata)
    assert len(result.connections_found) == 2
    users = {c.dst_user for c in result.connections_found}
    assert "root" in users
    assert "alice" in users


def test_src_ip_from_host_field(metadata):
    data = _make_utmp_record("bob", "10.10.0.7", 1710507900)
    result = WtmpParser().parse(data, metadata)
    assert result.connections_found[0].src_ip == "10.10.0.7"


def test_direction_context(metadata):
    data = _make_utmp_record("root", "10.10.0.1", 1710507720)
    result = WtmpParser().parse(data, metadata)
    assert result.connections_found[0].direction_context == "from_dst_logs"
    assert result.connections_found[0].dst_ip == "__upload_host__"


def test_non_login_records_skipped(metadata):
    # ut_type=1 is BOOT_TIME — should be skipped
    data = _make_utmp_record("reboot", "", 1710507720, ut_type=1)
    result = WtmpParser().parse(data, metadata)
    assert len(result.connections_found) == 0


def test_empty_file(metadata):
    result = WtmpParser().parse(b"", metadata)
    assert result.connections_found == []


def test_size_mismatch_warns(metadata):
    result = WtmpParser().parse(b"\x00" * 10, metadata)
    assert any("multiple" in w.lower() or "truncated" in w.lower() for w in result.warnings)
