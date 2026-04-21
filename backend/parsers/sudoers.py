"""Parser for /etc/sudoers and sudoers.d/* files.

Extracts sudo rules (user/group → run_as → commands) including NOPASSWD flags.
"""
from __future__ import annotations

import re

from parsers import BaseParser, ParseResult, SudoRuleData, UploadMetadata

# Matches: <subject> <host_spec>=(<run_as>) <commands>
# e.g. "alice ALL=(root) NOPASSWD: /bin/bash"
# e.g. "%sudo ALL=(ALL:ALL) NOPASSWD: ALL"
RULE_RE = re.compile(
    r'^(\S+)\s+\S+=\(([^)]+)\)\s+(.*)',
)

_SKIP_PREFIXES = (
    "@include",
    "#include",
    "Defaults",
    "Cmnd_Alias",
    "User_Alias",
    "Host_Alias",
    "Runas_Alias",
)


class SudoersParser(BaseParser):
    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Decode error: {e}")
            return result

        count = 0
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if any(stripped.startswith(prefix) for prefix in _SKIP_PREFIXES):
                continue

            m = RULE_RE.match(stripped)
            if not m:
                result.warnings.append(f"Skipped sudoers line: {stripped[:80]}")
                continue

            subject_raw = m.group(1)
            run_as_raw = m.group(2)
            cmds_raw = m.group(3)

            if subject_raw.startswith("%"):
                subject_type = "group"
                subject = subject_raw[1:]
            else:
                subject_type = "user"
                subject = subject_raw

            nopasswd = "NOPASSWD:" in cmds_raw
            commands = cmds_raw.replace("NOPASSWD:", "").strip()

            result.sudo_rules_found.append(SudoRuleData(
                subject=subject,
                subject_type=subject_type,
                run_as=run_as_raw,
                commands=commands,
                nopasswd=nopasswd,
                raw_line=stripped,
            ))
            count += 1

        result.stats = {"rules": count}
        return result
