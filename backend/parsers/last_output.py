"""Parser for the textual output of the `last` (and `lastb`) command.

`last` reads /var/log/wtmp and renders one line per session:

    user     line       host             start                end             duration
    kbrazil  pts/0      192.168.71.1     Tue Jan  5 20:03:51 2021   still logged in
    kbrazil  ttyS0                       Fri Feb 28 13:49 - 14:52  (01:56)
    reboot   system boot 5.8.0-...       Tue Jan  5 00:08:28 2021   still running

This parser walks lines and extracts ones that look like remote SSH
sessions:
- `user` is a real username (not `reboot`, `shutdown`, `runlevel`, `wtmp`, `utx.log`)
- `host` (third field) is non-empty AND looks like an IP / hostname

Bookkeeping lines (`reboot`, `shutdown`, footers like `wtmp begins ...`,
`utx.log begins ...`) are skipped — they don't represent connections.
"""
from __future__ import annotations

import re

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata

# A "remote-looking" host token: either a dotted-quad IP, an IPv6, or a
# hostname-looking string (must contain a dot OR be at least 3 chars and
# look like a name). Rules out `tty1`, `pts/0`, `ttyS0`, `console`,
# `system`, `boot`, kernel-version-like `5.8.0-34-generic`.
_HOST_REMOTE_RE = re.compile(
    r"^(?:"
    r"(?:\d{1,3}\.){3}\d{1,3}"               # IPv4
    r"|"
    r"[0-9a-fA-F:]+:[0-9a-fA-F:]+"            # IPv6 (very loose)
    r"|"
    r"[a-zA-Z][a-zA-Z0-9.\-]*\.[a-zA-Z0-9.\-]+"  # hostname with dot
    r")$"
)

# Username column values that are bookkeeping, not real users.
_BOOKKEEPING_USERS = frozenset({
    "reboot", "shutdown", "runlevel", "wtmp", "utx.log", "boot",
})

# tty / pts / virtual console patterns — the line column. If `host` looks
# like one of these tokens, treat it as the line and skip the record.
_LINE_LIKE_RE = re.compile(
    r"^(?:tty[A-Za-z0-9]*|pts/\d+|console|system|:\d+(?:\.\d+)?)$"
)

# Kernel version pattern (last column 3 of `reboot system boot 5.8.0-...`)
_KERNEL_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-\S+)?$")

# Footer / preamble lines that `last` emits: `wtmp begins ...`,
# `utx.log begins ...`, blank lines, etc.
_FOOTER_RE = re.compile(
    r"^(?:wtmp begins|btmp begins|utx\.log begins|btmp~|wtmp~)",
    re.IGNORECASE,
)


class LastOutputParser(BaseParser):
    """Parses the text output of the `last` command."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Decode error: {e}")
            return result

        records = 0
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue
            if _FOOTER_RE.match(line.strip()):
                continue

            # Tokenize on whitespace.
            tokens = line.split()
            if len(tokens) < 3:
                continue

            user = tokens[0]
            line_col = tokens[1]
            host_col = tokens[2]

            # Skip kernel reboot rows (`reboot system boot ...`).
            if user in _BOOKKEEPING_USERS:
                continue
            # Skip a line whose `line` column is `system` and `host` is `boot`
            # (extra defensiveness in case `user` was something odd).
            if line_col == "system" and host_col == "boot":
                continue

            # If host_col looks like a tty/pts (i.e. `last` was invoked without
            # the `-d` / hostname column), the session was local — skip.
            if _LINE_LIKE_RE.match(host_col):
                continue
            # Kernel version strings (e.g. `5.8.0-34-generic`) appear in the
            # host column for reboot rows; skip.
            if _KERNEL_VERSION_RE.match(host_col):
                continue

            # Validate host_col looks routable.
            if not _HOST_REMOTE_RE.match(host_col):
                continue

            conn = ConnectionData(
                src_ip=host_col,
                dst_ip="__upload_host__",
                connection_type="ssh",
                direction_context="from_dst_logs",
                dst_user=user,
                raw_line=raw_line[:512],
            )
            result.connections_found.append(conn)
            records += 1

        result.stats = {"records_parsed": records}
        return result
