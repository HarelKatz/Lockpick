"""Tests for wtmp parser."""
import os
import socket
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.wtmp import WtmpParser, _UTMP_SIZE, _UT_USER_PROCESS

# Independent, hardcoded glibc x86-64 `struct utmp` layout (384 bytes). Deliberately NOT
# parsers.wtmp._UTMP_FMT: packing test records with the parser's own format would round-trip
# green even if that format is wrong (the 382-vs-384 pad bug this suite must catch).
_TRUE_UTMP_FMT = "=h2xi32s4s32s256s4sl2l4i20s"
assert struct.calcsize(_TRUE_UTMP_FMT) == 384


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="wtmp",
        filename="wtmp",
    )


def _make_utmp_record(
    user: str,
    host: str,
    ts: int,
    ut_type: int = _UT_USER_PROCESS,
    addr_v6: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> bytes:
    """Build a minimal utmp record at the TRUE 384-byte layout (not the parser's format)."""
    return struct.pack(
        _TRUE_UTMP_FMT,
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
        *addr_v6,        # ut_addr_v6[4]
        b"\x00" * 20,    # __unused
    )


def _ipv4_words(ip: str) -> tuple[int, int, int, int]:
    """ut_addr_v6 words for an IPv4 login: address in word 0 (network order), rest zero."""
    return (struct.unpack("=i", socket.inet_aton(ip))[0], 0, 0, 0)


def _ipv6_words(ip: str) -> tuple[int, int, int, int]:
    """ut_addr_v6 words for an IPv6 login: the 16-byte address across all four words."""
    return struct.unpack("=4i", socket.inet_pton(socket.AF_INET6, ip))


def test_record_size_is_384():
    """The parser's record size must match the real glibc struct utmp (384 bytes), not 382."""
    assert _UTMP_SIZE == 384


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


def test_src_ip_from_addr_v6_ipv4(metadata):
    """When ut_host is empty, the IPv4 in ut_addr_v6[0] is the source IP."""
    data = _make_utmp_record("carol", "", 1710508000, addr_v6=_ipv4_words("10.20.0.5"))
    result = WtmpParser().parse(data, metadata)
    assert result.connections_found[0].src_ip == "10.20.0.5"


def test_src_ip_from_addr_v6_ipv6(metadata):
    """When ut_host is empty, an IPv6 address spanning all four ut_addr_v6 words is decoded."""
    data = _make_utmp_record("dave", "", 1710508100, addr_v6=_ipv6_words("2001:db8::1"))
    result = WtmpParser().parse(data, metadata)
    assert result.connections_found[0].src_ip == "2001:db8::1"


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


def test_utmp_magic_values_in_ut_host_skipped(metadata):
    """Real wtmp files contain console-login records where ut_host is
    'consLOGIN' / 'LOGIN' — these are bookkeeping, not SSH logins."""
    data = (
        _make_utmp_record("root", "consLOGIN", 1710507720)
        + _make_utmp_record("bob", "LOGIN", 1710507730)
        + _make_utmp_record("alice", "10.10.0.9", 1710507800)  # real login
    )
    result = WtmpParser().parse(data, metadata)
    assert len(result.connections_found) == 1
    assert result.connections_found[0].dst_user == "alice"
    assert result.connections_found[0].src_ip == "10.10.0.9"


def test_utmp_magic_values_in_ut_user_skipped(metadata):
    """Some wtmp records have ut_user='LOGIN' (getty) — those aren't SSH sessions."""
    data = _make_utmp_record("LOGIN", "10.10.0.5", 1710507720)
    result = WtmpParser().parse(data, metadata)
    assert result.connections_found == []
