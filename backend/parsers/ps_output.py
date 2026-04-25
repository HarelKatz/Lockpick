"""Parser for `ps aux` / `ps -ef` / `ps auxf` output.

Two harvest paths:

1. SSH/SCP/RSYNC cmdlines → ConnectionData (observed — process running).
2. Cmdlines with embedded secrets (`mysql -p<password>`, `curl -u user:pass`,
   `psql ... password=`, etc.) → CredentialData (cred_type=password).

Kernel threads (cmdline starts with `[`) and known-noise daemons are skipped
to avoid emitting spurious records.
"""
from __future__ import annotations

import gzip
import re

from parsers import (
    BaseParser,
    ConnectionData,
    CredentialData,
    ParseResult,
    UploadMetadata,
)

# `ps aux` cmdline columns:  USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
# `ps -ef` cmdline columns:  UID PID PPID C STIME TTY TIME COMMAND
# We sniff the header to decide which layout we have.
_PS_AUX_CMD_INDEX = 10
_PS_EF_CMD_INDEX = 7

# ssh-style commands.  We capture the user@host token if present.
# Alternation is left-to-right and `\b` matches between `h` and `-`, so
# `ssh-copy-id` must come before `ssh` (longest-first) — otherwise the
# regex matches `ssh` and mis-classifies it as a plain ssh connection.
_SSH_CMD_RE = re.compile(
    r"\b(?P<tool>ssh-copy-id|ssh|scp|rsync|sftp)\b"
)
# `user@host` or `host` after the ssh tool token.  We accept hostnames or IPs.
_USER_HOST_RE = re.compile(
    r"(?:^|\s)(?:(?P<user>[A-Za-z0-9._-]+)@)?(?P<host>[A-Za-z0-9.][A-Za-z0-9.-]*[A-Za-z0-9])(?::|$|\s)"
)

# Credential harvest patterns.  Anchored to common tools so we don't mass-tag
# every `--password` token in unrelated tools.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # mysql -p<password>  (no space — `-p` immediately followed)
    (re.compile(r"\bmysql\b[^\n]*\s-p(?P<v>[^\s]+)"), "mysql_password"),
    # mysql --password=<secret>
    (re.compile(r"\bmysql\b[^\n]*--password=(?P<v>[^\s]+)"), "mysql_password"),
    # psql 'postgres://user:pass@...'  → captured via PG_URL_RE below
    # psql ... password=<secret>
    (re.compile(r"\bpsql\b[^\n]*\bpassword=(?P<v>[^\s'\"]+)"), "psql_password"),
    # curl -u user:pass
    (re.compile(r"\bcurl\b[^\n]*\s-u\s+(?P<v>[^\s]+)"), "curl_basic_auth"),
    # curl --user user:pass
    (re.compile(r"\bcurl\b[^\n]*--user[= ]\s*(?P<v>[^\s]+)"), "curl_basic_auth"),
    # wget --password=<secret>
    (re.compile(r"\bwget\b[^\n]*--password=(?P<v>[^\s]+)"), "wget_password"),
    # ftp/lftp -u user,pass
    (re.compile(r"\blftp\b[^\n]*-u\s+(?P<v>[^\s]+)"), "lftp_credentials"),
    # sshpass -p <secret>
    (re.compile(r"\bsshpass\b[^\n]*-p\s*(?P<v>[^\s]+)"), "sshpass_password"),
    # sshpass -p<secret> (no space)
    (re.compile(r"\bsshpass\b[^\n]*-p(?P<v>[^\s\-][^\s]*)"), "sshpass_password"),
]
# postgres://user:pass@host or mysql://user:pass@host
_DB_URL_RE = re.compile(
    r"(?P<scheme>(?:postgres(?:ql)?|mysql|mongodb|redis|amqp|rabbitmq))://"
    r"(?P<userinfo>[^/@\s]+:[^/@\s]+)@"
)


def _is_kernel_thread(cmdline: str) -> bool:
    return cmdline.strip().startswith("[")


def _ps_layout(header: str) -> int | None:
    """Inspect the header row and return the index of the COMMAND column.

    Returns None if we can't identify the layout (we'll skip cred harvest
    in that case).
    """
    upper = header.upper().split()
    if not upper or "COMMAND" not in upper and "CMD" not in upper:
        return None
    try:
        if "COMMAND" in upper:
            idx = upper.index("COMMAND")
        else:
            idx = upper.index("CMD")
        return idx
    except ValueError:
        return None


class PsOutputParser(BaseParser):
    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

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
        if not lines:
            result.stats = {"connections": 0, "credentials": 0}
            return result

        # First non-empty line is the header.
        header_idx = None
        for i, l in enumerate(lines):
            if l.strip():
                header_idx = i
                break
        if header_idx is None:
            result.stats = {"connections": 0, "credentials": 0}
            return result
        header = lines[header_idx]
        cmd_col = _ps_layout(header)

        connections = 0
        credentials = 0
        seen_creds: set[tuple[str, str]] = set()  # (name, value) dedup

        for raw_line in lines[header_idx + 1 :]:
            if not raw_line.strip():
                continue

            cmdline = self._extract_cmdline(raw_line, cmd_col)
            if not cmdline:
                continue
            if _is_kernel_thread(cmdline):
                continue

            user = self._extract_user(raw_line)

            # SSH-family connections — process running ssh = observed connection.
            m_ssh = _SSH_CMD_RE.search(cmdline)
            if m_ssh:
                tool = m_ssh.group("tool")
                conn_type = {
                    "ssh": "ssh",
                    "scp": "scp",
                    "rsync": "rsync",
                    "sftp": "sftp",
                    "ssh-copy-id": "ssh_copy_id",
                }.get(tool, "ssh")
                # Find user@host in the part of the cmdline AFTER the tool name
                tail = cmdline[m_ssh.end():]
                target = self._find_target(tail)
                if target:
                    target_user, target_host = target
                    result.connections_found.append(ConnectionData(
                        src_ip="__upload_host__",
                        dst_ip=target_host,
                        connection_type=conn_type,
                        direction_context="from_src_logs",
                        src_user=user,
                        dst_user=target_user,
                        raw_line=raw_line[:512],
                    ))
                    connections += 1

            # Credential harvest from cmdline.
            for pattern, label in _SECRET_PATTERNS:
                for m in pattern.finditer(cmdline):
                    val = m.group("v")
                    if not val or len(val) > 256:
                        continue
                    key = (label, val)
                    if key in seen_creds:
                        continue
                    seen_creds.add(key)
                    result.credentials_found.append(CredentialData(
                        cred_type="password",
                        value=val,
                        name=label,
                        username=user,
                        relationship_type="found_on_disk",
                    ))
                    credentials += 1
            # DB-URL secrets
            for m in _DB_URL_RE.finditer(cmdline):
                ui = m.group("userinfo")
                key = (f"{m.group('scheme')}_url", ui)
                if key in seen_creds:
                    continue
                seen_creds.add(key)
                result.credentials_found.append(CredentialData(
                    cred_type="password",
                    value=ui,
                    name=f"{m.group('scheme')}_url",
                    username=user,
                    relationship_type="found_on_disk",
                ))
                credentials += 1

        result.stats = {"connections": connections, "credentials": credentials}
        return result

    @staticmethod
    def _extract_cmdline(raw: str, cmd_col: int | None) -> str:
        """Slice off the COMMAND portion of a `ps` row.

        We rely on the column count to find where the cmdline begins;
        falling back to a permissive split if the layout looks weird.
        """
        if cmd_col is None:
            # Fallback: try the `ps -ef` layout (8 fields, COMMAND at idx 7),
            # then `ps aux` (11 fields, COMMAND at idx 10).
            for idx in (_PS_EF_CMD_INDEX, _PS_AUX_CMD_INDEX):
                parts = raw.split(None, idx)
                if len(parts) > idx:
                    return parts[idx]
            return ""
        parts = raw.split(None, cmd_col)
        if len(parts) > cmd_col:
            return parts[cmd_col]
        return ""

    @staticmethod
    def _extract_user(raw: str) -> str | None:
        """First column on `ps aux`/`ps -ef` is the user."""
        parts = raw.split(None, 1)
        if not parts:
            return None
        return parts[0]

    @staticmethod
    def _find_target(tail: str) -> tuple[str | None, str] | None:
        """Find the first plausible user@host or host token in the cmdline tail."""
        for m in _USER_HOST_RE.finditer(tail):
            host = m.group("host")
            # Skip option flags and non-host fragments
            if host.startswith("-"):
                continue
            if "." not in host and not host.isalnum():
                continue
            # Must contain a letter or look like an IPv4
            if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", host) or re.search(r"[A-Za-z]", host):
                return (m.group("user"), host)
        return None
