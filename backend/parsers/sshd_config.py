"""Parser for /etc/ssh/sshd_config files."""
from __future__ import annotations

from parsers import BaseParser, ParseResult, UploadMetadata

_TRACKED_KEYS = {"port", "permitrootlogin", "passwordauthentication"}


class SshdConfigParser(BaseParser):
    """Parses /etc/ssh/sshd_config — creates HostUser records for AllowUsers entries."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        allow_users: list[str] = []
        allow_groups: list[str] = []
        deny_users: list[str] = []
        config: dict[str, str] = {}

        for lineno, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # Match blocks can override earlier directives with complex conditionals —
            # stop parsing to avoid misattributing Match-scoped values to the global config.
            if line.lower().startswith("match "):
                result.warnings.append(
                    f"Line {lineno}: Match block encountered — remaining directives not parsed"
                )
                break

            parts = line.split(None, 1)
            if len(parts) < 2:
                continue

            key = parts[0].lower()
            value = parts[1].strip()

            if key == "allowusers":
                allow_users.extend(value.split())
            elif key == "allowgroups":
                allow_groups.extend(value.split())
            elif key == "denyusers":
                deny_users.extend(value.split())
            elif key in _TRACKED_KEYS:
                config[key] = value

        # Emit HostUser records for AllowUsers (strip user@host patterns)
        for entry in allow_users:
            uname = entry.split("@")[0] if "@" in entry else entry
            result.host_users_found.append((uname, None, None))

        # Build stats — only include keys that were present in the file
        stats: dict = {}
        if allow_users:
            stats["allow_users"] = allow_users
        if allow_groups:
            stats["allow_groups"] = allow_groups
        if deny_users:
            stats["deny_users"] = deny_users
        stats.update(config)
        result.stats = stats

        return result
