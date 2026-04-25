"""Parser for legacy ~/.boto config files.

Format: INI with [Credentials] section holding aws_access_key_id /
aws_secret_access_key (and optional gs_* / euca_* equivalents for GCS
or Eucalyptus). [Boto] holds non-secret behaviour. Proxy passwords may
appear under [Boto] as `proxy_pass`.
"""
from __future__ import annotations

import configparser

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata
from parsers.aws_config import _filter_ini_lines

# Keys we treat as secret material (across multiple cloud aliases)
_SECRET_KEYS = (
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
    "gs_access_key_id",
    "gs_secret_access_key",
    "euca_access_key_id",
    "euca_secret_access_key",
    "proxy_pass",
)


class BotoParser(BaseParser):
    """Parses legacy ~/.boto config — emits credentials per secret key found."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        # Filter out non-INI-shaped lines (bare `...` continuation markers seen
        # in legacy boto docs) so configparser doesn't choke on them.
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
            for key in _SECRET_KEYS:
                value = lower.get(key)
                if not value:
                    continue
                # Optional: associate proxy_pass with proxy_user as username
                username = None
                if key == "proxy_pass":
                    username = (lower.get("proxy_user") or "").strip() or None
                result.credentials_found.append(
                    CredentialData(
                        cred_type="password",
                        value=value,
                        username=username,
                        relationship_type="found_on_disk",
                        name=f"boto:{section}:{key}",
                    )
                )
                creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
