"""Parser for rclone config files (~/.config/rclone/rclone.conf).

INI format with one section per remote. Per-section type-specific secrets:
- s3: access_key_id, secret_access_key, session_token
- azureblob: key, sas_url (account is the storage-account *username*, paired)
- swift: key, auth_token (user is the username, paired)
- onedrive / dropbox / google drive: token (JSON blob)
- ftp / sftp: pass, key_pem
- crypt: password, password2 (these are obscured by rclone, but still secrets)
- webdav: pass, bearer_token (user is the webdav username, paired)
- b2: key (account is the b2 account ID, paired as username)
- mega: pass (user is the username, paired)
- generic: anything matching `*_pass`, `password`, `secret*`, `token*`
"""
from __future__ import annotations

import configparser

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata
from parsers.aws_config import _filter_ini_lines

# Per-type known secret keys. `user`/`account` fields are NOT included here —
# they are usernames, not secrets, and are paired onto secret credentials below.
_SECRET_KEYS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "s3": ("access_key_id", "secret_access_key", "session_token"),
    "azureblob": ("key", "sas_url", "service_principal_file"),
    "swift": ("key", "auth_token"),
    "onedrive": ("token",),
    "dropbox": ("token",),
    "drive": ("token", "service_account_credentials"),
    "googlecloudstorage": ("token", "service_account_credentials"),
    "ftp": ("pass",),
    "sftp": ("pass", "key_pem", "key_file_pass"),
    "crypt": ("password", "password2"),
    "webdav": ("pass", "bearer_token"),
    "b2": ("key",),
    "mega": ("pass",),
    "pcloud": ("token",),
    "box": ("token",),
}

# Map from section_type → name of the field that holds the username-like
# identifier. Values from these fields are paired as `CredentialData.username`
# on each secret credential emitted from the section, never emitted as a
# standalone password credential.
_USERNAME_FIELD_BY_TYPE: dict[str, str] = {
    "swift": "user",
    "azureblob": "account",
    "b2": "account",
    "webdav": "user",
    "mega": "user",
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

            # Username-like identifier for this section (e.g. swift's `user`,
            # azureblob's `account`). Paired as username on each emitted secret.
            username_field = _USERNAME_FIELD_BY_TYPE.get(section_type)
            section_username: str | None = None
            if username_field:
                v = lower.get(username_field)
                if v:
                    section_username = v

            # Build the set of keys we'll harvest from this section.
            keys_to_harvest: set[str] = set()
            keys_to_harvest.update(_SECRET_KEYS_BY_TYPE.get(section_type, ()))
            for k in lower.keys():
                if _is_generic_secret(k):
                    keys_to_harvest.add(k)

            # Never emit the username-like field as a secret credential.
            if username_field:
                keys_to_harvest.discard(username_field)

            for key in keys_to_harvest:
                value = lower.get(key)
                if not value:
                    continue
                result.credentials_found.append(
                    CredentialData(
                        cred_type="password",
                        value=value,
                        username=section_username,
                        relationship_type="found_on_disk",
                        name=f"rclone:{section}:{key}",
                    )
                )
                creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
