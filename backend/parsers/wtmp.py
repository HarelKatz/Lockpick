"""Parser for wtmp binary login records."""
from __future__ import annotations

import socket
import struct
from datetime import datetime, timezone

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata

# utmp record size is 384 bytes on Linux x86_64. On-disk (32-bit-compat) layout —
# note the 2-byte alignment pad after ut_type, without which this drifts to 382:
#   short    ut_type;                              // 2  + 2 pad
#   int32_t  ut_pid;                               // 4
#   char     ut_line[32];
#   char     ut_id[4];
#   char     ut_user[32];
#   char     ut_host[256];
#   struct exit_status ut_exit;                    // 4  (2 shorts)
#   int32_t  ut_session;                           // 4
#   struct { int32_t tv_sec, tv_usec; } ut_tv;     // 8  (32-bit compat, NOT 8-byte longs)
#   int32_t  ut_addr_v6[4];                        // 16
#   char     __unused[20];
_UTMP_FMT = "=h2xi32s4s32s256s4sl2l4i20s"
_UTMP_SIZE = struct.calcsize(_UTMP_FMT)

_UT_USER_PROCESS = 7   # USER_PROCESS: normal login
_UT_LOGIN_PROCESS = 6  # LOGIN_PROCESS: getty / terminal login

# utmp writes these magic values into ut_user / ut_host for records that don't
# represent a remote login (console logins, runlevel transitions, reboots).
# Matching either field on one of these values means the record is not a
# real SSH-style login and should be skipped.
_UTMP_MAGIC_VALUES = frozenset({
    "consLOGIN", "LOGIN", "RUNLEVEL", "REBOOT", "SHUTDOWN",
    "BOOT_TIME", "NEW_TIME", "OLD_TIME", "~", "~~",
})


def _decode_str(b: bytes) -> str:
    return b.rstrip(b"\x00").decode("utf-8", errors="replace").strip()


def _addr_to_ip(addr_v6: list[int]) -> str | None:
    """Convert ut_addr_v6 to an IP string, or None if unset.

    The address is stored in network byte order across four int32 words. Per the
    glibc / util-linux convention an IPv4 login populates only word 0 (the rest
    zero); IPv6 uses all four. Re-pack the words to their raw bytes so inet_ntop
    can format the correct family.
    """
    if all(a == 0 for a in addr_v6):
        return None
    raw = struct.pack("=4i", *addr_v6)
    if addr_v6[1] == addr_v6[2] == addr_v6[3] == 0:
        return socket.inet_ntop(socket.AF_INET, raw[:4])
    return socket.inet_ntop(socket.AF_INET6, raw)


class WtmpParser(BaseParser):
    """Parses binary wtmp / btmp files (Linux utmp format)."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        if len(content) % _UTMP_SIZE != 0:
            result.warnings.append(
                f"File size {len(content)} is not a multiple of utmp record size {_UTMP_SIZE} — "
                "may be truncated or wrong format"
            )

        records = 0
        for offset in range(0, len(content) - _UTMP_SIZE + 1, _UTMP_SIZE):
            chunk = content[offset : offset + _UTMP_SIZE]
            if len(chunk) < _UTMP_SIZE:
                break
            try:
                fields = struct.unpack(_UTMP_FMT, chunk)
            except struct.error as e:
                result.warnings.append(f"Failed to unpack record at offset {offset}: {e}")
                continue

            (
                ut_type, ut_pid, ut_line, ut_id,
                ut_user, ut_host,
                ut_exit,
                ut_session,
                tv_sec, tv_usec,
                *addr_v6_and_pad,
            ) = fields
            addr_v6 = list(addr_v6_and_pad[:4])

            if ut_type not in (_UT_USER_PROCESS, _UT_LOGIN_PROCESS):
                continue

            user = _decode_str(ut_user)
            host = _decode_str(ut_host)
            if not user:
                continue
            # Skip utmp bookkeeping records masquerading as logins (console
            # logins, runlevel transitions, reboots). Real SSH logins have a
            # username in ut_user and either an empty or real-hostname ut_host.
            if user in _UTMP_MAGIC_VALUES or host in _UTMP_MAGIC_VALUES:
                continue

            ts = None
            if tv_sec > 0:
                try:
                    ts = datetime.fromtimestamp(tv_sec, tz=timezone.utc).isoformat()
                except (OSError, OverflowError):
                    pass

            src_ip = host if host else _addr_to_ip(addr_v6)
            if not src_ip:
                src_ip = "unknown"

            conn = ConnectionData(
                src_ip=src_ip,
                dst_ip="__upload_host__",
                connection_type="ssh",
                direction_context="from_dst_logs",
                dst_user=user,
                timestamp=ts,
                raw_line=f"wtmp: {user} from {src_ip}",
            )
            result.connections_found.append(conn)
            records += 1

        result.stats = {"records_parsed": records}
        return result
