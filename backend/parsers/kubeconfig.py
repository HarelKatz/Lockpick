"""Parser for kubeconfig YAML files (~/.kube/config).

Format: YAML with `users` list, each user has a `user` block that may
contain:
- `token` — a bearer token (password credential)
- `client-certificate-data` — base64-encoded PEM client cert (informational)
- `client-key-data` — base64-encoded PEM client private key (private_key credential)
- `client-certificate` / `client-key` — file paths (no inline secret to capture)
- `password` — basic auth password
- `username` — basic auth username (paired with password)
- `auth-provider.config.refresh-token` / `id-token` — oauth-ish tokens

We harvest tokens, decoded client-key, and basic-auth password.
Defensive against multi-doc YAML, REDACTED placeholders, and malformed input.
"""
from __future__ import annotations

import base64
import binascii

import yaml

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata

# Strings that the wild commonly substitutes for real key material
_PLACEHOLDERS = {"REDACTED", "DATA+OMITTED", "OMITTED", ""}


def _decode_b64_key(b64: str) -> str | None:
    """Decode base64 client-key-data. Returns the PEM text or None on failure."""
    if not isinstance(b64, str):
        return None
    if b64.strip().upper() in _PLACEHOLDERS:
        return None
    try:
        raw = base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        return None
    try:
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def _yaml_load_all(text: str) -> tuple[list[dict], list[str]]:
    """Load every YAML doc; return list of dicts plus warnings for failed docs."""
    docs: list[dict] = []
    warns: list[str] = []
    try:
        for d in yaml.safe_load_all(text):
            if isinstance(d, dict):
                docs.append(d)
    except yaml.YAMLError as e:
        warns.append(f"YAML parse error: {e}")
    return docs, warns


class KubeconfigParser(BaseParser):
    """Parses kubeconfig YAML — emits per-user tokens, basic-auth passwords, and decoded client keys."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        docs, warns = _yaml_load_all(text)
        result.warnings.extend(warns)

        creds_found = 0
        for doc in docs:
            users = doc.get("users")
            if not isinstance(users, list):
                continue
            for user_entry in users:
                if not isinstance(user_entry, dict):
                    continue
                user_name = user_entry.get("name") or "user"
                user = user_entry.get("user")
                if not isinstance(user, dict):
                    continue

                # Bearer token
                token = user.get("token")
                if isinstance(token, str) and token.strip() and token.strip().upper() not in _PLACEHOLDERS:
                    result.credentials_found.append(
                        CredentialData(
                            cred_type="password",
                            value=token,
                            username=user_name,
                            relationship_type="found_on_disk",
                            name=f"kubeconfig:{user_name}:token",
                        )
                    )
                    creds_found += 1

                # client-key-data — base64 PEM private key
                key_b64 = user.get("client-key-data")
                if isinstance(key_b64, str) and key_b64.strip():
                    pem = _decode_b64_key(key_b64)
                    if pem and "PRIVATE KEY" in pem:
                        result.credentials_found.append(
                            CredentialData(
                                cred_type="private_key",
                                value=pem,
                                username=user_name,
                                relationship_type="found_on_disk",
                                name=f"kubeconfig:{user_name}:client_key",
                            )
                        )
                        creds_found += 1
                    elif key_b64.strip().upper() not in _PLACEHOLDERS:
                        result.warnings.append(
                            f"User '{user_name}': client-key-data did not decode to a PEM private key"
                        )

                # Basic auth password (legacy)
                password = user.get("password")
                if isinstance(password, str) and password.strip():
                    basic_user = user.get("username") or user_name
                    result.credentials_found.append(
                        CredentialData(
                            cred_type="password",
                            value=password,
                            username=str(basic_user),
                            relationship_type="found_on_disk",
                            name=f"kubeconfig:{user_name}:password",
                        )
                    )
                    creds_found += 1

                # auth-provider tokens (refresh-token / id-token)
                ap = user.get("auth-provider")
                if isinstance(ap, dict):
                    cfg = ap.get("config")
                    if isinstance(cfg, dict):
                        for k in ("refresh-token", "id-token", "access-token"):
                            v = cfg.get(k)
                            if isinstance(v, str) and v.strip() and v.strip().upper() not in _PLACEHOLDERS:
                                result.credentials_found.append(
                                    CredentialData(
                                        cred_type="password",
                                        value=v,
                                        username=user_name,
                                        relationship_type="found_on_disk",
                                        name=f"kubeconfig:{user_name}:{k.replace('-', '_')}",
                                    )
                                )
                                creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
