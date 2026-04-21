"""Parser for /etc/sudoers and sudoers.d/* files.

Extracts sudo rules (user/group → run_as → commands) including NOPASSWD flags.
Handles:
  - Backslash continuation lines
  - Rules with run_as parens:  alice ALL=(root) NOPASSWD: /bin/bash
  - Rules without parens:      jack  CSNETS = ALL
  - Group subjects:            %wheel ALL=(ALL) ALL
  - Netgroup subjects:         +secretaries ALL = PRINTING
"""
from __future__ import annotations

import re

from parsers import BaseParser, ParseResult, SudoRuleData, UploadMetadata

# Matches: <subject>  <host_spec> [=|= ] (<run_as>) <rest>
# Handles both "ALL=(root)" and "ALL = (root)" (space around =)
# e.g. "alice ALL=(root) NOPASSWD: /bin/bash"
# e.g. "%sudo ALL=(ALL:ALL) NOPASSWD: ALL"
# e.g. "fred ALL = (DB) NOPASSWD: ALL"
# e.g. "bob SPARC=(OP) ALL : SGI=(OP) ALL"   (multi-host specs — we just grab first)
_RULE_WITH_RUNAS = re.compile(r'^(\S+)\s+\S+\s*=\s*\(([^)]+)\)\s+(.*)')

# Matches: <subject>  <host>[_spec] = <rest>  (no parens around run_as)
# e.g. "jack CSNETS = ALL"
# e.g. "FULLTIMERS  ALL = NOPASSWD: ALL"
# e.g. "ALL     CDROM = NOPASSWD: /sbin/umount /CDROM"
_RULE_NO_RUNAS = re.compile(r'^(\S+)\s+\S+\s*=\s*(.*)')

# Lines that start with these tokens are not user-spec rules
_SKIP_PREFIXES = (
    "@include",
    "@includedir",
    "#include",
    "Defaults",
    "Cmnd_Alias",
    "User_Alias",
    "Host_Alias",
    "Runas_Alias",
)


def _join_continuations(text: str) -> list[str]:
    """Join lines ending with backslash into a single logical line."""
    raw_lines = text.splitlines()
    joined: list[str] = []
    buf = ""
    for raw in raw_lines:
        stripped_raw = raw.rstrip()
        if stripped_raw.endswith("\\"):
            buf += stripped_raw[:-1] + " "
        else:
            buf += stripped_raw
            joined.append(buf.strip())
            buf = ""
    if buf.strip():
        joined.append(buf.strip())
    return joined


class SudoersParser(BaseParser):
    """Parses /etc/sudoers — creates SudoRuleData records."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Decode error: {e}")
            return result

        count = 0
        for line in _join_continuations(text):
            if not line or line.startswith("#"):
                continue
            if any(line.startswith(prefix) for prefix in _SKIP_PREFIXES):
                continue

            # Try with run_as parens first
            m = _RULE_WITH_RUNAS.match(line)
            if m:
                subject_raw = m.group(1)
                run_as_raw = m.group(2)
                cmds_raw = m.group(3)
            else:
                # Fall back to no-parens form
                m2 = _RULE_NO_RUNAS.match(line)
                if not m2:
                    result.warnings.append(f"Skipped sudoers line: {line[:80]}")
                    continue
                subject_raw = m2.group(1)
                run_as_raw = "ALL"
                cmds_raw = m2.group(2)

            # Determine subject type
            if subject_raw.startswith("%"):
                subject_type = "group"
                subject = subject_raw[1:]
            else:
                subject_type = "user"
                subject = subject_raw

            nopasswd = "NOPASSWD:" in cmds_raw
            commands = re.sub(r"\s*NOPASSWD:\s*", "", cmds_raw).strip()

            result.sudo_rules_found.append(SudoRuleData(
                subject=subject,
                subject_type=subject_type,
                run_as=run_as_raw,
                commands=commands,
                nopasswd=nopasswd,
                raw_line=line,
            ))
            count += 1

        result.stats = {"rules": count}
        return result
