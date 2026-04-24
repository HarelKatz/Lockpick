"""Parser for /etc/shadow files."""
from __future__ import annotations

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata

# Hash values that carry no usable credential
_NO_HASH_SENTINELS = {"", "x", "!!"}
# Bare locked markers (no recoverable hash follows)
_BARE_LOCKED = {"*", "!"}


class ShadowParser(BaseParser):
    """Parses /etc/shadow — creates HostUser records and password-hash Credentials."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        creds_found = 0
        users_found = 0

        for lineno, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split(":")
            if len(parts) < 2:
                result.warnings.append(
                    f"Line {lineno}: expected at least 2 fields, got {len(parts)}, skipping"
                )
                continue

            username = parts[0].strip()
            hash_val = parts[1]

            if not username:
                result.warnings.append(f"Line {lineno}: empty username, skipping")
                continue

            # No usable hash — service/system account, skip HostUser
            if hash_val in _NO_HASH_SENTINELS:
                if hash_val == "x":
                    result.warnings.append(
                        f"User '{username}': password shadowed (x placeholder) — no hash available"
                    )
                continue

            # Bare locked marker with no recoverable hash — skip HostUser
            if hash_val in _BARE_LOCKED:
                result.warnings.append(f"User '{username}': account is locked ({hash_val}) — no hash")
                continue

            # Locked account with a recoverable hash (e.g. "!$6$salt$hash..." or "!!$6$salt$hash...")
            if hash_val.startswith("!") and len(hash_val) > 1:
                actual_hash = hash_val.lstrip("!")
                result.warnings.append(
                    f"User '{username}': locked account with recoverable hash — leading '!' stripped"
                )
            else:
                actual_hash = hash_val

            result.host_users_found.append((username, None, None))
            users_found += 1

            result.credentials_found.append(
                CredentialData(
                    cred_type="password",
                    value=actual_hash,
                    username=username,
                    relationship_type="found_on_disk",
                    name=f"shadow hash for {username}",
                )
            )
            creds_found += 1

        result.stats = {"hashes_found": creds_found, "users_found": users_found}
        return result
