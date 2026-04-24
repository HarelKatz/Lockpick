"""Parser for auth.log / secure files (optionally gzip-compressed)."""
from __future__ import annotations

import gzip
import re
from datetime import datetime, timezone

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata

# Patterns for sshd log lines
# Accepted publickey for root from 10.0.0.5 port 12345 ssh2: RSA SHA256:abc...
_ACCEPTED_RE = re.compile(
    r"Accepted\s+(?P<method>\S+)\s+for\s+(?P<user>\S+)\s+from\s+(?P<ip>\S+)"
    r"(?:\s+port\s+\d+)?"
)
# Fingerprint anywhere on the line after the initial match
_FP_RE = re.compile(r"(?P<fp>SHA256:[A-Za-z0-9+/=]+)")
# Disconnect / session closed lines (ignored, but we can still skip gracefully)

# Timestamp at start of syslog lines: "Mar 15 14:22:00" or ISO "2024-03-15T14:22:00"
_SYSLOG_TS_RE = re.compile(
    r"^(?P<ts>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
)

_AUTH_METHODS = {"publickey", "password", "keyboard-interactive", "hostbased"}


def _normalise_method(raw: str) -> str:
    raw = raw.lower().strip()
    return raw if raw in _AUTH_METHODS else "unknown"


def _parse_ts(ts_str: str) -> str | None:
    for fmt in ("%b %d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(ts_str.strip(), fmt)
            # syslog lines lack the year — use current year as best guess
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now(timezone.utc).year)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


class AuthLogParser(BaseParser):
    """Parses sshd auth.log / secure files, including .gz compressed versions."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        # Decompress if gzip
        if content[:2] == b"\x1f\x8b":
            try:
                content = gzip.decompress(content)
            except Exception as e:
                result.warnings.append(f"Failed to decompress gzip: {e}")
                return result

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        accepted = 0
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            if "sshd" not in raw_line:
                continue

            ts_str = None
            m_ts = _SYSLOG_TS_RE.match(raw_line)
            if m_ts:
                ts_str = _parse_ts(m_ts.group("ts"))

            m = _ACCEPTED_RE.search(raw_line)
            if m:
                method = _normalise_method(m.group("method"))
                fp_m = _FP_RE.search(raw_line)
                conn = ConnectionData(
                    src_ip=m.group("ip"),
                    dst_ip="__upload_host__",
                    connection_type="ssh",
                    direction_context="from_dst_logs",
                    dst_user=m.group("user"),
                    auth_method=method,
                    timestamp=ts_str,
                    raw_line=raw_line[:512],
                    credential_fingerprint=fp_m.group("fp") if fp_m else None,
                )
                result.connections_found.append(conn)
                accepted += 1
                continue

        result.stats = {
            "lines_parsed": len(text.splitlines()),
            "accepted_logins": accepted,
            "total_records": len(result.connections_found),
        }
        return result
