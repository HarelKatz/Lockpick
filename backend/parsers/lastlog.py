"""Parser for /var/log/lastlog binary records (Linux).

Linux lastlog format — one fixed-size record per UID, indexed by UID:

    struct lastlog {
        int32_t  ll_time;          // 4   bytes  unix epoch (last login)
        char     ll_line[32];      // 32  bytes  tty / pts line
        char     ll_host[256];     // 256 bytes  remote hostname / IP (may be blank)
    };

Record size: 292 bytes. UID = offset / 292. A "never logged in" UID has an
all-zero record and is skipped. Only records with ll_time != 0 are emitted —
the username is the UID itself if no /etc/passwd is available, but since
parsers don't have DB access here, the user field is left as "uid:<n>" so
the upload pipeline can attach it (or the operator can correlate).
"""
from __future__ import annotations

import struct
from datetime import datetime, timezone

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata

# Linux lastlog record: int32 ll_time, 32-byte ll_line, 256-byte ll_host
_LASTLOG_FMT = "=I32s256s"
_LASTLOG_SIZE = struct.calcsize(_LASTLOG_FMT)
assert _LASTLOG_SIZE == 292, f"lastlog record size sanity check failed: {_LASTLOG_SIZE}"


def _decode_str(b: bytes) -> str:
    return b.rstrip(b"\x00").decode("utf-8", errors="replace").strip()


class LastlogParser(BaseParser):
    """Parses binary /var/log/lastlog files."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        if len(content) == 0:
            result.stats = {"records_parsed": 0, "uids_with_login": 0}
            return result

        if len(content) % _LASTLOG_SIZE != 0:
            result.warnings.append(
                f"File size {len(content)} is not a multiple of lastlog record size "
                f"{_LASTLOG_SIZE} — may be truncated or wrong format"
            )

        records = 0
        for offset in range(0, len(content) - _LASTLOG_SIZE + 1, _LASTLOG_SIZE):
            chunk = content[offset : offset + _LASTLOG_SIZE]
            uid = offset // _LASTLOG_SIZE

            # Skip "never logged in" slots (all zeros).
            if chunk == b"\x00" * _LASTLOG_SIZE:
                continue

            try:
                ll_time, ll_line, ll_host = struct.unpack(_LASTLOG_FMT, chunk)
            except struct.error as e:
                result.warnings.append(f"Failed to unpack record uid={uid}: {e}")
                continue

            # ll_time == 0 means the slot was zeroed but other bytes survived;
            # treat it as "never logged in" too.
            if ll_time == 0:
                continue

            line = _decode_str(ll_line)
            host = _decode_str(ll_host)

            ts = None
            try:
                ts = datetime.fromtimestamp(ll_time, tz=timezone.utc).isoformat()
            except (OSError, OverflowError, ValueError):
                pass

            # If ll_host is empty the login was local (tty/console); skip — the
            # upload pipeline cannot resolve a non-existent source IP and we
            # don't want phantom hosts.
            if not host:
                continue

            conn = ConnectionData(
                src_ip=host,
                dst_ip="__upload_host__",
                connection_type="ssh",
                direction_context="from_dst_logs",
                dst_user=f"uid:{uid}",
                timestamp=ts,
                raw_line=f"lastlog: uid={uid} from {host} on {line}",
            )
            result.connections_found.append(conn)
            records += 1

        result.stats = {
            "records_parsed": records,
            "uids_with_login": records,
        }
        return result
