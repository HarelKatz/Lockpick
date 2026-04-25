"""Parser for MySQL/MariaDB client config files (.my.cnf, /etc/mysql/my.cnf, etc.).

INI format with sections like [client], [mysql], [mysqldump]. Credentials
appear as `password = ...`, `user = ...`, optionally with `host = ...`.

Notes
-----
- We treat the line `password = my_password` (case-insensitive on the key,
  whitespace tolerant around `=`) as a credential ONLY when the value is
  non-empty.
- We harvest from any section. Server-only sections like [mysqld] may also
  store a default password, so we don't restrict to [client]/[mysql].
"""
from __future__ import annotations

import configparser
import io

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata


class MysqlConfigParser(BaseParser):
    """Parses .my.cnf and emits one CredentialData per section that has a password."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        # configparser stumbles on bare keys (no `=`) like `quick`, on
        # `!includedir` directives, and on duplicate keys. Use lenient mode
        # and tolerate parse failures section-by-section.
        cp = configparser.RawConfigParser(
            allow_no_value=True,
            strict=False,
            interpolation=None,
        )
        # Filter out lines configparser will reject:
        #   - `!include` / `!includedir` directives
        #   - bare flag lines that confuse it (we don't need them)
        # We'll keep `key` (no value) lines because allow_no_value=True handles them.
        cleaned: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("!"):
                continue
            cleaned.append(line)

        try:
            cp.read_string("\n".join(cleaned))
        except configparser.Error as e:
            result.warnings.append(f"INI parse error: {e}")
            # Keep going — cp may have populated some sections before failing
            return result

        creds_found = 0
        for section in cp.sections():
            try:
                items = dict(cp.items(section))
            except configparser.Error as e:
                result.warnings.append(f"Section [{section}]: {e}")
                continue

            # Normalize key lookup (case-insensitive)
            lower = {k.lower(): v for k, v in items.items()}
            password = lower.get("password")
            if not password:
                continue
            password = password.strip()
            # Strip optional surrounding quotes
            if (password.startswith('"') and password.endswith('"')) or (
                password.startswith("'") and password.endswith("'")
            ):
                password = password[1:-1]
            if not password:
                continue

            user = (lower.get("user") or "").strip() or None
            host = (lower.get("host") or "").strip() or None
            label = host if host else section
            name = f"mysql:{label}"

            result.credentials_found.append(
                CredentialData(
                    cred_type="password",
                    value=password,
                    username=user,
                    relationship_type="found_on_disk",
                    name=name,
                )
            )
            creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
