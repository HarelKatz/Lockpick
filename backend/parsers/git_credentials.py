"""Parser for ~/.git-credentials (git credential.helper=store format).

Format: one URL per line: `https://user:pass@host/path` or with port.
URL-encoded — we decode user/pass via urllib.parse.unquote.
"""
from __future__ import annotations

from urllib.parse import urlsplit, unquote

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata


class GitCredentialsParser(BaseParser):
    """Parses ~/.git-credentials — emits password CredentialData per URL line."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        creds_found = 0
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            try:
                parts = urlsplit(line)
            except Exception as e:
                result.warnings.append(f"Line {lineno}: URL parse error: {e}")
                continue

            if not parts.scheme or not parts.hostname:
                result.warnings.append(f"Line {lineno}: not a valid URL, skipping")
                continue

            user = unquote(parts.username) if parts.username else None
            password = unquote(parts.password) if parts.password else None

            if not password:
                result.warnings.append(f"Line {lineno}: no password in URL, skipping")
                continue

            host = parts.hostname
            result.credentials_found.append(
                CredentialData(
                    cred_type="password",
                    value=password,
                    username=user,
                    relationship_type="found_on_disk",
                    name=f"git:{host}",
                )
            )
            creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
