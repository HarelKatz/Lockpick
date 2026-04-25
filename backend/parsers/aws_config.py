"""Parser for ~/.aws/config.

Usually no credentials — `region`, `output`, `role_arn` etc. only.
Emit CredentialData ONLY if a section actually contains secret values
(aws_session_token, aws_access_key_id, aws_secret_access_key — yes,
old configs sometimes inline these).
"""
from __future__ import annotations

import configparser

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata


def _filter_ini_lines(text: str) -> str:
    """Drop lines that aren't INI-shaped (bare markers, `...`, prose blurb).

    Keeps section headers, key=value/key:value lines, blanks, and # / ;
    comments. Anything else is silently removed before configparser sees it.
    """
    cleaned: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        if stripped.startswith(("#", ";")):
            cleaned.append(line)
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            cleaned.append(line)
            continue
        if "=" in stripped or ":" in stripped:
            cleaned.append(line)
            continue
    return "\n".join(cleaned)

# Keys that store actual secret material
_SECRET_KEYS = {
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
}


def _profile_label(section: str) -> str:
    """`[profile dev]` → `dev`; `[default]` → `default`."""
    s = section.strip()
    if s.startswith("profile "):
        return s[len("profile "):].strip()
    return s


class AwsConfigParser(BaseParser):
    """Parses ~/.aws/config — emits credentials only if secrets are inlined."""

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
            profile = _profile_label(section)
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
