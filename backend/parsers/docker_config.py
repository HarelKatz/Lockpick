"""Parser for ~/.docker/config.json.

Format:
    {
      "auths": {
        "registry.example.com": {"auth": "BASE64(user:pass)"},
        "https://index.docker.io/v1/": {"auth": "..."}
      },
      "credsStore": "secretservice",   # external credential helper — no inline secret
      "credHelpers": {"reg": "helper"} # ditto
    }

Emit one CredentialData per `auths.<registry>` entry where `auth` is set
and base64-decodes to `user:pass`.
"""
from __future__ import annotations

import base64
import binascii
import json

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata


def _decode_auth(b64: str) -> tuple[str | None, str | None]:
    """Decode base64 'user:pass'. Returns (user, pass) or (None, None) on failure."""
    if not isinstance(b64, str) or not b64.strip():
        return None, None
    try:
        raw = base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        return None, None
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return None, None
    if ":" not in text:
        return None, None
    user, _, pw = text.partition(":")
    return user, pw


class DockerConfigParser(BaseParser):
    """Parses ~/.docker/config.json — emits CredentialData for inline registry auth."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            result.warnings.append(f"Invalid JSON: {e}")
            result.stats = {"credentials": 0}
            return result

        if not isinstance(data, dict):
            result.warnings.append("Expected JSON object at top level")
            result.stats = {"credentials": 0}
            return result

        creds_found = 0
        auths = data.get("auths")
        if isinstance(auths, dict):
            for registry, entry in auths.items():
                if not isinstance(entry, dict):
                    continue
                # Inline auth field
                auth_b64 = entry.get("auth")
                if isinstance(auth_b64, str) and auth_b64.strip():
                    user, pw = _decode_auth(auth_b64)
                    if pw:
                        result.credentials_found.append(
                            CredentialData(
                                cred_type="password",
                                value=pw,
                                username=user or None,
                                relationship_type="found_on_disk",
                                name=f"docker:{registry}",
                            )
                        )
                        creds_found += 1
                    else:
                        result.warnings.append(
                            f"Registry '{registry}': could not decode `auth` value"
                        )
                # Some configs split user/pass into separate fields
                username = entry.get("username")
                password = entry.get("password")
                if (
                    isinstance(password, str)
                    and password.strip()
                    and not (isinstance(auth_b64, str) and auth_b64.strip())
                ):
                    result.credentials_found.append(
                        CredentialData(
                            cred_type="password",
                            value=password,
                            username=username if isinstance(username, str) else None,
                            relationship_type="found_on_disk",
                            name=f"docker:{registry}",
                        )
                    )
                    creds_found += 1

        # credsStore / credHelpers carry no inline secrets — skip silently
        result.stats = {"credentials": creds_found}
        return result
