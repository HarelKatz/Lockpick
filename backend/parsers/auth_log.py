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

# Timestamp at start of syslog lines: "Mar 15 14:22:00" or ISO "2024-03-15T14:22:00"
_SYSLOG_TS_RE = re.compile(
    r"^(?P<ts>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
)

_AUTH_METHODS = {"publickey", "password", "keyboard-interactive", "hostbased"}

# strptime yields this year when the format carries no year (classic syslog) — the
# marker that a timestamp needs file-aware year inference (see _resolve_syslog_years).
_YEARLESS = 1900


def _now() -> datetime:
    """Reference 'now' for syslog year inference.

    Isolated so tests (and the real_examples snapshot suite) can freeze it —
    otherwise inferred years, and the committed snapshots, would drift with the
    wall clock.
    """
    return datetime.now(timezone.utc)


def _normalise_method(raw: str) -> str:
    raw = raw.lower().strip()
    return raw if raw in _AUTH_METHODS else "unknown"


def _parse_ts_raw(ts_str: str) -> datetime | None:
    """Parse a leading syslog/ISO timestamp to a naive datetime, or None.

    Classic syslog ("Mar 15 14:22:00") carries no year, so strptime returns year
    _YEARLESS (1900); ISO timestamps carry a real year. Year inference for the
    yearless ones happens later, file-aware, in _resolve_syslog_years.
    """
    for fmt in ("%b %d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _safe_replace_year(dt: datetime, year: int) -> datetime | None:
    try:
        return dt.replace(year=year)
    except ValueError:  # Feb 29 landing on a non-leap inferred year
        return None


def _resolve_syslog_years(
    yearless: list[datetime], now: datetime
) -> list[datetime | None]:
    """Assign a year to each yearless (year==_YEARLESS) syslog timestamp.

    `yearless` are the parsed datetimes in file order. Logs are assumed
    chronologically ascending (true for syslog / auth.log / journalctl): anchor
    the newest entry to `now`'s year (or the previous year if that would place it
    in the future), then walk backward, dropping a year each time an earlier
    line's month is greater than the following line's (a Dec->Jan crossing seen
    going back in time). Returns a parallel list (None where Feb-29 can't map).
    """
    n = len(yearless)
    if n == 0:
        return []
    ref = now.replace(tzinfo=None)  # naive, comparable to strptime output (both UTC)

    last = yearless[-1]
    cand = _safe_replace_year(last, ref.year)
    year = ref.year if (cand is not None and cand <= ref) else ref.year - 1

    out: list[datetime | None] = [None] * n
    out[n - 1] = _safe_replace_year(last, year)
    for i in range(n - 2, -1, -1):
        if yearless[i].month > yearless[i + 1].month:
            year -= 1
        out[i] = _safe_replace_year(yearless[i], year)
    return out


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

        lines = text.splitlines()

        # Phase 1 — collect Accepted logins with their raw (possibly yearless) timestamp.
        entries: list[dict] = []
        for raw_line in lines:
            if "sshd" not in raw_line:
                continue
            m = _ACCEPTED_RE.search(raw_line)
            if not m:
                continue
            raw_dt: datetime | None = None
            m_ts = _SYSLOG_TS_RE.match(raw_line)
            if m_ts:
                raw_dt = _parse_ts_raw(m_ts.group("ts"))
            fp_m = _FP_RE.search(raw_line)
            entries.append(
                {
                    "src_ip": m.group("ip"),
                    "user": m.group("user"),
                    "method": _normalise_method(m.group("method")),
                    "fingerprint": fp_m.group("fp") if fp_m else None,
                    "raw_line": raw_line[:512],
                    "raw_dt": raw_dt,
                }
            )

        # Phase 2 — resolve the year for the yearless (classic-syslog) timestamps,
        # in file order, then splice the resolved datetimes back by index.
        yearless_idx = [
            i
            for i, e in enumerate(entries)
            if e["raw_dt"] is not None and e["raw_dt"].year == _YEARLESS
        ]
        resolved = _resolve_syslog_years(
            [entries[i]["raw_dt"] for i in yearless_idx], _now()
        )
        for i, dt in zip(yearless_idx, resolved):
            entries[i]["raw_dt"] = dt

        # Phase 3 — materialize connections.
        for e in entries:
            dt = e["raw_dt"]
            timestamp = (
                dt.replace(tzinfo=timezone.utc).isoformat() if dt is not None else None
            )
            result.connections_found.append(
                ConnectionData(
                    src_ip=e["src_ip"],
                    dst_ip="__upload_host__",
                    connection_type="ssh",
                    direction_context="from_dst_logs",
                    dst_user=e["user"],
                    auth_method=e["method"],
                    timestamp=timestamp,
                    raw_line=e["raw_line"],
                    credential_fingerprint=e["fingerprint"],
                )
            )

        result.stats = {
            "lines_parsed": len(lines),
            "accepted_logins": len(entries),
            "total_records": len(result.connections_found),
        }
        return result
