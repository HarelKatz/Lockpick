"""Parser for GCP Application Default Credentials JSON.

Two flavours:
- `authorized_user` / `external_account_authorized_user`:
    {"client_id": ..., "client_secret": ..., "refresh_token": ..., "type": ...}
  → emit a password CredentialData with refresh_token as the secret.
- `service_account`:
    {"type": "service_account", "private_key": "-----BEGIN ...", "client_email": ..., ...}
  → emit a private_key CredentialData with the PEM body.

Names always include client_email when present, otherwise client_id.
"""
from __future__ import annotations

import json

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata


class GcloudCredentialsParser(BaseParser):
    """Parses GCP ADC JSON files."""

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

        cred_type_field = data.get("type")
        ident = data.get("client_email") or data.get("client_id") or "gcp"

        creds_found = 0

        if cred_type_field == "service_account":
            private_key = data.get("private_key")
            if isinstance(private_key, str) and private_key.strip():
                result.credentials_found.append(
                    CredentialData(
                        cred_type="private_key",
                        value=private_key,
                        username=None,
                        relationship_type="found_on_disk",
                        name=f"gcp:service_account:{ident}",
                    )
                )
                creds_found += 1
            else:
                result.warnings.append(
                    "service_account JSON missing 'private_key' field"
                )
        else:
            # Authorized-user style (or external_account_authorized_user)
            refresh_token = data.get("refresh_token")
            if isinstance(refresh_token, str) and refresh_token.strip():
                result.credentials_found.append(
                    CredentialData(
                        cred_type="password",
                        value=refresh_token,
                        username=None,
                        relationship_type="found_on_disk",
                        name=f"gcp:refresh_token:{ident}",
                    )
                )
                creds_found += 1
            else:
                # Some external_account JSON just hold a token URL — nothing
                # to harvest. That's fine; emit no warning.
                pass

            # client_secret is also sensitive (oauth client). Capture if present.
            client_secret = data.get("client_secret")
            if isinstance(client_secret, str) and client_secret.strip():
                result.credentials_found.append(
                    CredentialData(
                        cred_type="password",
                        value=client_secret,
                        username=None,
                        relationship_type="found_on_disk",
                        name=f"gcp:client_secret:{ident}",
                    )
                )
                creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
