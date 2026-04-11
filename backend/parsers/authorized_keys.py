"""Parser for .ssh/authorized_keys files."""
from __future__ import annotations

import base64
import hashlib

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata


def _fingerprint(key_b64: str) -> str | None:
    """Compute SHA256 fingerprint from base64-encoded key blob."""
    try:
        raw = base64.b64decode(key_b64)
        digest = hashlib.sha256(raw).digest()
        b64 = base64.b64encode(digest).decode().rstrip("=")
        return f"SHA256:{b64}"
    except Exception:
        return None


class AuthorizedKeysParser(BaseParser):
    """Parses .ssh/authorized_keys — one public key per line."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        username = metadata.username
        filename = metadata.filename or "authorized_keys"

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        keys_found = 0
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 2:
                result.warnings.append(f"Line {lineno}: too few fields, skipping")
                continue

            # authorized_keys format: [options] keytype base64key [comment]
            # Detect if first token is a key type or options
            known_types = {
                "ssh-rsa", "ssh-dss", "ssh-ed25519", "ecdsa-sha2-nistp256",
                "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
                "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com",
            }

            # skip options prefix if present
            idx = 0
            if parts[0] not in known_types:
                # skip options token(s) until we hit a key type
                while idx < len(parts) and parts[idx] not in known_types:
                    idx += 1

            if idx >= len(parts) - 1:
                result.warnings.append(f"Line {lineno}: unrecognised format, skipping")
                continue

            key_b64 = parts[idx + 1]
            fingerprint = _fingerprint(key_b64)

            cred = CredentialData(
                cred_type="public_key",
                value=line,
                username=username,
                relationship_type="authorized_key",
                name=f"authorized_key from {filename}" + (f" ({username})" if username else ""),
            )
            result.credentials_found.append(cred)
            keys_found += 1

            if fingerprint is None:
                result.warnings.append(f"Line {lineno}: could not compute fingerprint for key")

        if username:
            # Record that this user account exists on the host
            result.host_users_found.append((username, None, None))

        result.stats = {"keys_parsed": keys_found}
        return result
