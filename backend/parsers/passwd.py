"""Parser for /etc/passwd files."""
from __future__ import annotations

from parsers import BaseParser, ParseResult, UploadMetadata

# Shells that indicate a real interactive login
_LOGIN_SHELLS = {
    "/bin/bash", "/bin/sh", "/bin/zsh", "/bin/fish", "/bin/ksh", "/bin/tcsh",
    "/usr/bin/bash", "/usr/bin/zsh", "/usr/bin/fish", "/usr/bin/ksh",
    "/usr/local/bin/bash", "/usr/local/bin/zsh",
}
_NOLOGIN_SHELLS = {"/sbin/nologin", "/usr/sbin/nologin", "/bin/false", "/bin/nologin"}


def _is_login_user(uid: int, shell: str) -> bool:
    """Keep root and any account with uid >= 1000 that has a real login shell."""
    if uid == 0:
        return True  # always keep root
    if uid < 1000:
        return False
    return shell not in _NOLOGIN_SHELLS


class PasswdParser(BaseParser):
    """Parses /etc/passwd — creates HostUser records (no credentials, no connections)."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        filename = metadata.filename or "passwd"

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

            parts = line.split(":")
            if len(parts) < 7:
                result.warnings.append(f"Line {lineno}: expected 7 fields, got {len(parts)}, skipping")
                continue

            username, password, uid_str, gid_str, gecos, home_dir, shell = parts[:7]
            try:
                uid = int(uid_str)
            except ValueError:
                result.warnings.append(f"Line {lineno}: invalid UID '{uid_str}', skipping")
                continue

            if not _is_login_user(uid, shell):
                continue

            # (username, shell, home_dir) — router will create/update HostUser
            result.host_users_found.append((username, shell, home_dir))
            found += 1

        result.stats = {"users_parsed": found}
        return result
