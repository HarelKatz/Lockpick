"""Parser for zsh extended history files.

Format (extended):

    : <epoch>:<duration>;<command>

A multi-line command may use a trailing backslash on the previous line to
continue. We extract ssh-family commands the same way bash_history does,
but also capture the timestamp from the leading `: <epoch>:` prefix.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata

# zsh extended-history line: `: 1700000000:0;some command`
_HEADER_RE = re.compile(r"^:\s+(?P<epoch>\d+):\d+;(?P<cmd>.*)$")

# Same SSH-family extraction approach as shell_rc / bash_history.
# NOTE: each `_SSH_CMD_RE` hit must be validated by `_is_real_cmd_match`
# below — `\b` matches inside `ssh-keygen`/`ssh-add` and unrelated words,
# which would otherwise produce phantom connections.
_SSH_CMD_RE = re.compile(r"\b(?P<cmd>ssh-copy-id|ssh|scp|rsync|sftp)\b")

# See shell_rc._is_real_cmd_match for rationale.
_VALID_PREFIX_CHARS = frozenset(" \t=\"'`(;&|!")
_INVALID_SUFFIX_CHARS = frozenset("-_")


def _quoted_spans(line: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if c in ("'", '"') and (i == 0 or line[i - 1] != "\\"):
            quote = c
            j = i + 1
            while j < n:
                if line[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if line[j] == quote:
                    spans.append((i, j, quote))
                    i = j + 1
                    break
                j += 1
            else:
                break
        else:
            i += 1
    return spans


def _is_real_cmd_match(
    line: str,
    cmd_m: "re.Match[str]",
    spans: list[tuple[int, int, str]] | None = None,
) -> bool:
    start = cmd_m.start()
    end = cmd_m.end()
    if start > 0 and line[start - 1] not in _VALID_PREFIX_CHARS:
        return False
    if end < len(line) and line[end] in _INVALID_SUFFIX_CHARS:
        return False
    if spans is None:
        spans = _quoted_spans(line)
    for q_start, q_end, _ in spans:
        if q_start < start < q_end:
            if start != q_start + 1:
                return False
    return True
_HOST_PART = r"(?:(?:\d{1,3}\.){3}\d{1,3}|(?=[a-zA-Z0-9_.\-]*[a-zA-Z])[a-zA-Z0-9_.\-]+)"
_USER_HOST_RE = re.compile(
    r"(?P<token>(?:(?P<user>[a-zA-Z0-9_.\-]+)@)?"
    rf"(?P<host>{_HOST_PART})"
    r"(?::\d+)?)$"
)

_CMD_MAP = {
    "ssh": "ssh",
    "scp": "scp",
    "rsync": "rsync",
    "sftp": "sftp",
    "ssh-copy-id": "ssh_copy_id",
}

_SKIP_HOSTS = {"localhost", "127.0.0.1", "::1", ""}

_FLAG_TAKES_ARG = frozenset({
    "-l", "-p", "-i", "-o", "-F", "-J", "-D", "-L", "-R",
    "-W", "-c", "-m", "-Q", "-S", "-w", "-O", "-E", "-e", "-b",
})


def _extract_destination(tail: str) -> tuple[str | None, str | None]:
    """Find a (user, host) destination from a token sequence after an ssh-family cmd."""
    tokens = tail.split()
    user = None
    host = None

    # First pass: any token containing `@`.
    for t in tokens:
        if "@" in t and not t.startswith("-"):
            head = t.split(":", 1)[0]
            m = _USER_HOST_RE.match(head)
            if m and m.group("user") and m.group("host"):
                return m.group("user"), m.group("host")

    # Second pass: walk tokens, skipping flags, looking for a bare host token.
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("-"):
            if t in _FLAG_TAKES_ARG:
                if t == "-l" and i + 1 < len(tokens):
                    user = tokens[i + 1]
                i += 2
                continue
            i += 1
            continue
        if "/" in t or t.startswith("."):
            i += 1
            continue
        m = _USER_HOST_RE.match(t)
        if m:
            host = m.group("host")
            if m.group("user"):
                user = m.group("user")
            break
        i += 1

    return user, host


class ZshHistoryParser(BaseParser):
    """Parses .zsh_history (extended format with `: <epoch>:<dur>;<cmd>`)."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        src_user = metadata.username

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        lines = text.splitlines()
        # Reassemble multi-line commands (trailing backslash).
        cmds: list[tuple[str | None, str]] = []  # (timestamp_iso, command)
        i = 0
        while i < len(lines):
            line = lines[i]
            m = _HEADER_RE.match(line)
            if m:
                epoch = int(m.group("epoch"))
                cmd_text = m.group("cmd")
                # Continuation: lines ending with `\` join into one command.
                while cmd_text.endswith("\\") and i + 1 < len(lines):
                    i += 1
                    cmd_text = cmd_text[:-1] + "\n" + lines[i]
                ts = None
                try:
                    ts = datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
                except (OSError, OverflowError, ValueError):
                    pass
                cmds.append((ts, cmd_text))
            # Lines that don't match the header are ignored — they're either
            # plain (non-extended) history lines we cannot timestamp, or
            # garbage (the goyalankit sample is a Ruby script).
            i += 1

        ssh_count = 0
        for ts, cmd in cmds:
            spans = _quoted_spans(cmd)
            for cmd_m in _SSH_CMD_RE.finditer(cmd):
                if not _is_real_cmd_match(cmd, cmd_m, spans):
                    continue
                cmd_raw = cmd_m.group("cmd")
                conn_type = _CMD_MAP.get(cmd_raw, "ssh")
                tail = cmd[cmd_m.end():]
                tail = re.split(r"[;|&\n]", tail, maxsplit=1)[0]
                user, host = _extract_destination(tail)
                if not host or host in _SKIP_HOSTS:
                    continue
                conn = ConnectionData(
                    src_ip="__upload_host__",
                    dst_ip=host,
                    connection_type=conn_type,
                    direction_context="from_src_logs",
                    src_user=src_user,
                    dst_user=user,
                    timestamp=ts,
                    raw_line=cmd[:512],
                )
                result.connections_found.append(conn)
                ssh_count += 1

        result.stats = {
            "commands_parsed": len(cmds),
            "ssh_commands": ssh_count,
        }
        return result
