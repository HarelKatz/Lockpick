"""Parser for .bash_history files."""
from __future__ import annotations

import re

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata

# Match: ssh [-l user] [-p port] [user@]host  (and scp/rsync/sftp/ssh-copy-id)
_SSH_RE = re.compile(
    r"(?P<cmd>ssh|scp|rsync|sftp|ssh-copy-id)"
    r"(?:\s+[^;|&\n]*)?"         # optional flags (greedy but stops at shell ops)
    r"\s+"
    r"(?:(?P<user>[a-zA-Z0-9_.\-]+)@)?(?P<host>[a-zA-Z0-9_.\-]+(?::\d+)?)"
)
# -l flag for user: ssh -l root host
_L_FLAG_RE = re.compile(r"-l\s+(?P<user>[a-zA-Z0-9_.\-]+)")
# -p flag for port: ssh -p 2222 host
_P_FLAG_RE = re.compile(r"-p\s+(?P<port>\d+)")

_CMD_MAP = {
    "ssh": "ssh",
    "scp": "scp",
    "rsync": "rsync",
    "sftp": "sftp",
    "ssh-copy-id": "ssh_copy_id",
}

# Skip localhost / empty
_SKIP_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


class BashHistoryParser(BaseParser):
    """Parses .bash_history — extracts SSH-family commands as outbound connection indicators."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        filename = metadata.filename or "bash_history"
        src_user = metadata.username

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        found = 0
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            m = _SSH_RE.search(line)
            if not m:
                # Note keygen / ssh-add as context
                if re.search(r"\bssh-keygen\b|\bssh-add\b", line):
                    result.warnings.append(
                        f"Line {lineno}: ssh-keygen/ssh-add usage noted (key management activity)"
                    )
                continue

            cmd_raw = m.group("cmd")
            conn_type = _CMD_MAP.get(cmd_raw, "ssh")

            host = m.group("host") or ""
            # strip trailing port-like :number from host if not already separate
            host = host.split(":")[0]
            if not host or host in _SKIP_HOSTS:
                continue

            user_from_at = m.group("user")
            # also try -l flag
            l_m = _L_FLAG_RE.search(line)
            user = user_from_at or (l_m.group("user") if l_m else None)

            conn = ConnectionData(
                src_ip="__upload_host__",
                dst_ip=host,
                connection_type=conn_type,
                direction_context="from_src_logs",
                src_user=src_user,
                dst_user=user,
                raw_line=raw_line[:512],
            )
            result.connections_found.append(conn)
            found += 1

        result.stats = {"commands_parsed": found}
        return result
