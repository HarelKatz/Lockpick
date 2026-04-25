"""Parser for ~/.aws/credentials.

Format: per-profile INI with aws_access_key_id, aws_secret_access_key,
optionally aws_session_token. Emits one CredentialData per secret value
(access key, secret key, session token).
"""
from __future__ import annotations

import configparser

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata
from parsers.aws_config import _filter_ini_lines

# Order matters for stable output / readability
_SECRET_KEYS = (
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
)


class AwsCredentialsParser(BaseParser):
    """Parses ~/.aws/credentials — emits one CredentialData per secret per profile."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        cleaned = _filter_ini_lines(text)
        cp = configparser.RawConfigParser(strict=False, interpolation=None)
        try:
            cp.read_string(cleaned)
        except configparser.Error as e:
            result.warnings.append(f"INI parse error: {e}")
            return result

        creds_found = 0
        for section in cp.sections():
            try:
                items = dict(cp.items(section))
            except configparser.Error as e:
                result.warnings.append(f"Section [{section}]: {e}")
                continue
            lower = {k.lower(): v.strip() for k, v in items.items()}
            profile = section.strip()
            for key in _SECRET_KEYS:
                value = lower.get(key)
                if not value:
                    continue
                result.credentials_found.append(
                    CredentialData(
                        cred_type="password",
                        value=value,
                        username=None,
                        relationship_type="found_on_disk",
                        name=f"aws:{profile}:{key}",
                    )
                )
                creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
