"""Parser for rclone config files (~/.config/rclone/rclone.conf).

INI format with one section per remote. Per-section type-specific secrets:
- s3: access_key_id, secret_access_key, session_token
- azureblob: account, key, sas_url
- swift: user, key
- onedrive / dropbox / google drive: token (JSON blob)
- ftp / sftp: pass, key_pem
- crypt: password, password2 (these are obscured by rclone, but still secrets)
- generic: anything matching `*_pass`, `password`, `secret*`, `token*`
"""
from __future__ import annotations

import configparser

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata
from parsers.aws_config import _filter_ini_lines

# Per-type known secret keys
_SECRET_KEYS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "s3": ("access_key_id", "secret_access_key", "session_token"),
    "azureblob": ("account", "key", "sas_url"),
    "swift": ("user", "key"),
    "onedrive": ("token",),
    "dropbox": ("token",),
    "drive": ("token", "service_account_credentials"),
    "googlecloudstorage": ("token", "service_account_credentials"),
    "ftp": ("pass",),
    "sftp": ("pass", "key_pem", "key_file_pass"),
    "crypt": ("password", "password2"),
    "webdav": ("user", "pass", "bearer_token"),
    "b2": ("account", "key"),
    "mega": ("user", "pass"),
    "pcloud": ("token",),
    "box": ("token",),
}

# Generic field-name patterns recognised regardless of type
_GENERIC_SECRET_KEYS = {
    "password",
    "password2",
    "pass",
    "secret",
    "secret_access_key",
    "token",
    "bearer_token",
    "client_secret",
    "key_pem",
}


def _is_generic_secret(key: str) -> bool:
    k = key.lower()
    if k in _GENERIC_SECRET_KEYS:
        return True
    # Suffix match on `_pass`, `_secret`, `_token`
    if k.endswith("_pass") or k.endswith("_secret") or k.endswith("_token"):
        return True
    return False


class RcloneConfigParser(BaseParser):
    """Parses rclone INI — emits per-section secret CredentialData."""

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
            section_type = (lower.get("type") or "").strip().lower()

            # Build the set of keys we'll harvest from this section.
            keys_to_harvest: set[str] = set()
            keys_to_harvest.update(_SECRET_KEYS_BY_TYPE.get(section_type, ()))
            for k in lower.keys():
                if _is_generic_secret(k):
                    keys_to_harvest.add(k)

            for key in keys_to_harvest:
                value = lower.get(key)
                if not value:
                    continue
                # 'user' is only sensitive for some backends — when it appears
                # alongside an actual password key we pair it as username
                if key in ("user", "account") and section_type not in ("swift", "azureblob", "b2", "webdav", "mega"):
                    continue
                result.credentials_found.append(
                    CredentialData(
                        cred_type="password",
                        value=value,
                        username=None,
                        relationship_type="found_on_disk",
                        name=f"rclone:{section}:{key}",
                    )
                )
                creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
