"""Parser for .ssh/authorized_keys files."""
from __future__ import annotations

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata

# Key types we recognise as the start of the key material. A line whose first
# top-level token is not one of these is treated as having an options prefix.
_KNOWN_TYPES = {
    "ssh-rsa", "ssh-dss", "ssh-ed25519", "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com",
}


def _partition_top_level_ws(s: str) -> tuple[str, bool, str]:
    """Split `s` at the first whitespace that is *outside* double quotes.

    Returns (head, found, rest). authorized_keys options are a comma-separated
    list in which a value may be a double-quoted string containing spaces, commas
    and backslash-escaped quotes — so the options prefix can only be delimited by
    quote-aware scanning, never by str.split().
    """
    in_quote = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and in_quote and i + 1 < len(s):
            i += 2  # backslash-escaped char inside a quoted value
            continue
        if c == '"':
            in_quote = not in_quote
        elif not in_quote and c.isspace():
            return s[:i], True, s[i + 1:]
        i += 1
    return s, False, ""


def _split_options_and_key(line: str) -> tuple[str | None, str]:
    """Split an authorized_keys line into (options_or_None, key material)."""
    head, found, rest = _partition_top_level_ws(line)
    if not found or head in _KNOWN_TYPES:
        return None, line
    return head, rest.lstrip()


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

            # authorized_keys format: [options] keytype base64key [comment]
            options, key_part = _split_options_and_key(line)
            key_tokens = key_part.split()

            if len(key_tokens) < 2:
                result.warnings.append(f"Line {lineno}: too few fields, skipping")
                continue
            if key_tokens[0] not in _KNOWN_TYPES:
                result.warnings.append(f"Line {lineno}: unrecognised format, skipping")
                continue

            cred = CredentialData(
                cred_type="public_key",
                value=" ".join(key_tokens),  # keytype base64 [comment] — no options prefix
                username=username,
                relationship_type="authorized_key",
                name=f"authorized_key from {filename}" + (f" ({username})" if username else ""),
                key_options=options,
            )
            result.credentials_found.append(cred)
            keys_found += 1

        if username:
            # Record that this user account exists on the host
            result.host_users_found.append((username, None, None))

        result.stats = {"keys_parsed": keys_found}
        return result
