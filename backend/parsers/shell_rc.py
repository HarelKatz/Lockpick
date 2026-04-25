"""Parser for shell rc files (.bashrc, .zshrc).

Aggressive harvest:

* SSH-family commands (`ssh`, `scp`, `rsync`, `sftp`, `ssh-copy-id`) — even
  when wrapped in `alias x=`. Emitted as outbound ConnectionData against
  the upload host.
* Exported secrets — `export FOO_PASSWORD=...`, `*_TOKEN=...`, `*_SECRET=...`,
  `*_API_KEY=...`, `AWS_*=...`, `*_DSN=...`. Emitted as CredentialData with
  cred_type=password and the env var name as the human-readable label.

Lines beginning with `#` are skipped. Values quoted with single/double
quotes have the outer pair stripped. Values that are obvious shell
expansions (`$VAR`, `$(cmd)`, `` `cmd` ``) are ignored — they don't carry
a literal secret in the file.
"""
from __future__ import annotations

import re

from parsers import (
    BaseParser,
    ConnectionData,
    CredentialData,
    ParseResult,
    UploadMetadata,
)

# An ssh-family command keyword sitting at a word boundary. Used to chunk a
# line into invocations; the rest of each chunk is parsed for `[user@]host`.
# NOTE: this regex by itself is not enough — `\b` matches between `h` and `-`
# in `ssh-keygen`/`ssh-add`, and unrelated words can satisfy `\b` boundaries
# too. Each match must be validated by `_is_real_cmd_match()` below.
_SSH_CMD_RE = re.compile(r"\b(?P<cmd>ssh-copy-id|ssh|scp|rsync|sftp)\b")

# Characters that are valid immediately before an ssh-family command keyword:
# start-of-line, whitespace, or a shell separator/quote/assignment. Anything
# else (e.g. inside an unrelated word like `xssh` or `myssh`) is a false hit.
_VALID_PREFIX_CHARS = frozenset(" \t=\"'`(;&|!")
# Characters that, if they appear immediately AFTER the matched keyword,
# mean this is a different command (e.g. `ssh-keygen`, `ssh-add`,
# `ssh-agent`, `ssh-keyscan`, `ssh-import-id`, `ssh_foo`).
_INVALID_SUFFIX_CHARS = frozenset("-_")


def _quoted_spans(line: str) -> list[tuple[int, int, str]]:
    """Return a list of (start, end, quote_char) for every quoted span in `line`.

    Naive but sufficient for shell-rc / shell-history use: scans the string
    left-to-right, opens a span on `'` or `"` that isn't backslash-escaped,
    and closes it on the next matching unescaped quote. Backticks aren't
    treated as quote spans here (they're already filtered as dynamic values
    elsewhere). Unterminated quotes yield no span.
    """
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
                # Unterminated quote — bail.
                break
        else:
            i += 1
    return spans


def _is_real_cmd_match(
    line: str,
    cmd_m: "re.Match[str]",
    spans: list[tuple[int, int, str]] | None = None,
) -> bool:
    """Validate that an `_SSH_CMD_RE` hit is a real ssh-family invocation.

    Rejects:
    - Matches inside larger identifiers (`ssh-keygen`, `xssh`): suffix `-`/`_`
      check, and prefix-char check against a known set of shell separators.
    - Matches inside a quoted string that DOES NOT begin with the keyword
      (e.g. `echo "running ssh tunnel"` — `ssh` is several chars into the
      `"..."` span). Aliases of the form `alias x='ssh user@host'` ARE
      accepted because the keyword sits immediately after the opening quote.
    """
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
            # Match is inside a quoted span. Accept only if the keyword
            # starts right after the opening quote (alias-style invocation).
            if start != q_start + 1:
                return False
    return True
# `[user@]host[:port]` token. Host is either a dotted IPv4 OR a hostname
# containing at least one letter (rules out flag args like `2222`).
_HOST_PART = r"(?:(?:\d{1,3}\.){3}\d{1,3}|(?=[a-zA-Z0-9_.\-]*[a-zA-Z])[a-zA-Z0-9_.\-]+)"
_USER_HOST_RE = re.compile(
    r"(?P<token>(?:(?P<user>[a-zA-Z0-9_.\-]+)@)?"
    rf"(?P<host>{_HOST_PART})"
    r"(?::\d+)?)$"
)
_L_FLAG_RE = re.compile(r"-l\s+(?P<user>[a-zA-Z0-9_.\-]+)")

# Secret-like env var name patterns. Case-insensitive; matched against the
# bare variable name (after `export ` stripped).
_SECRET_NAME_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r".*_PASSWORD$",
        r".*_PASS$",
        r".*_TOKEN$",
        r".*_SECRET$",
        r".*_API_KEY$",
        r".*_KEY$",
        r"^AWS_.*",
        r".*_DSN$",
    )
]
# Names matching these are NOT secrets (avoid false positives like
# SSH_AUTH_SOCK / `KEY_BINDINGS` / shell-internal `KEYTIMEOUT`).
_SECRET_NAME_DENYLIST = re.compile(
    r"^("
    r"SSH_AUTH_SOCK|SSH_AGENT_PID|GPG_TTY|KEYTIMEOUT|KEY_BINDINGS|"
    r"SSH_KEY_PATH|GPG_KEY_PATH|"
    r"PATH|HOME|SHELL|TERM|LANG|LC_.*|PS1|PS2|PROMPT|PROMPT_COMMAND|"
    r"HISTSIZE|HISTFILE|HISTCONTROL|HISTIGNORE|EDITOR|VISUAL|PAGER"
    r")$",
    re.IGNORECASE,
)

# `export NAME=value` or `NAME=value` (with optional `export`).
_EXPORT_RE = re.compile(
    r"^(?:export\s+)?(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*(?P<value>.+?)\s*$"
)

_CMD_MAP = {
    "ssh": "ssh",
    "scp": "scp",
    "rsync": "rsync",
    "sftp": "sftp",
    "ssh-copy-id": "ssh_copy_id",
}

_SKIP_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


def _strip_outer_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _is_dynamic_value(s: str) -> bool:
    """Return True if the value is obviously a shell expansion (no literal secret)."""
    if not s:
        return True
    # `$VAR`, `${VAR}`, `$(cmd)`, `` `cmd` ``
    if s.startswith("$") or s.startswith("`"):
        return True
    # Pure $(...) wrapper
    if s.startswith("$("):
        return True
    return False


def _is_secret_name(name: str) -> bool:
    if _SECRET_NAME_DENYLIST.match(name):
        return False
    return any(p.match(name) for p in _SECRET_NAME_PATTERNS)


class ShellRcParser(BaseParser):
    """Parses .bashrc / .zshrc — extracts ssh-family commands and exported secrets."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        src_user = metadata.username

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        ssh_count = 0
        secret_count = 0

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # SSH-family extraction (works even when nested inside `alias x='ssh ...'`).
            # 1. Find every ssh-family command keyword position.
            # 2. For each, scan tokens after the keyword until a shell separator
            #    or end of segment, picking the best-looking destination token.
            #    Preference order:
            #      a) any token containing `@` (definitely user@host[:path])
            #      b) for ssh-family commands, the first plain token that looks
            #         like [hostname-or-ip] and isn't a flag/local path/digit.
            spans = _quoted_spans(line)
            for cmd_m in _SSH_CMD_RE.finditer(line):
                if not _is_real_cmd_match(line, cmd_m, spans):
                    continue
                cmd_raw = cmd_m.group("cmd")
                conn_type = _CMD_MAP.get(cmd_raw, "ssh")
                tail = line[cmd_m.end():]
                # Stop at the next shell control char or quote boundary.
                tail = re.split(r"[;|&\n'\"]", tail, maxsplit=1)[0]

                tokens = tail.split()
                user = None
                host = None

                # First pass: any token containing `@` wins (user@host[:path]).
                for t in tokens:
                    if "@" in t and not t.startswith("-"):
                        # Strip a trailing :path (rsync/scp dest spec).
                        head = t.split(":", 1)[0]
                        m = _USER_HOST_RE.match(head)
                        if m and m.group("user") and m.group("host"):
                            user = m.group("user")
                            host = m.group("host")
                            break

                # Second pass: walk tokens, skipping flags and their
                # arguments, looking for a bare hostname token.
                if not host:
                    i = 0
                    flag_takes_arg = {
                        "-l", "-p", "-i", "-o", "-F", "-J", "-D", "-L", "-R",
                        "-W", "-c", "-m", "-Q", "-S", "-w", "-O", "-E", "-e", "-b",
                    }
                    while i < len(tokens):
                        t = tokens[i]
                        if t.startswith("-"):
                            if t in flag_takes_arg:
                                if t == "-l" and i + 1 < len(tokens):
                                    user = tokens[i + 1]
                                i += 2
                                continue
                            i += 1
                            continue
                        # Skip local file path tokens (contain `/` outside hostname).
                        if "/" in t or t.startswith("."):
                            i += 1
                            continue
                        m = _USER_HOST_RE.match(t)
                        if m:
                            user_at = m.group("user")
                            host = m.group("host")
                            if user_at:
                                user = user_at
                            break
                        i += 1

                if not host or host in _SKIP_HOSTS:
                    continue

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
                ssh_count += 1

            # Secret extraction: only consider "looks like an assignment" lines.
            m_exp = _EXPORT_RE.match(line)
            if m_exp:
                name = m_exp.group("name")
                value = _strip_outer_quotes(m_exp.group("value"))
                if not _is_secret_name(name):
                    continue
                if _is_dynamic_value(value):
                    continue

                cred = CredentialData(
                    cred_type="password",
                    value=value,
                    username=src_user,
                    name=name,
                    relationship_type="found_on_disk",
                )
                result.credentials_found.append(cred)
                secret_count += 1

        result.stats = {
            "ssh_commands": ssh_count,
            "secrets": secret_count,
        }
        return result
