"""Parser for ~/.netrc files (RFC 1738).

Format:
    machine HOSTNAME login USER password PASSWORD
    machine HOSTNAME
        login USER
        password PASSWORD

May also use `default` block (matches any host) or `account` keyword.
Tokens are whitespace-separated; can span multiple lines or be inline.
"""
from __future__ import annotations

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata

# Keywords introducing a new block
_BLOCK_KEYWORDS = {"machine", "default"}
# Keywords that take a value
_VALUE_KEYWORDS = {"machine", "login", "password", "account"}
# Tokens we recognise (anything else is a stray token; macdef body is special)
_KNOWN_KEYWORDS = _VALUE_KEYWORDS | {"default", "macdef"}


class NetrcParser(BaseParser):
    """Parses ~/.netrc and emits one password CredentialData per machine block."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        # Tokenize the entire file into whitespace-separated tokens.
        # We must skip macdef bodies — they continue until a blank line.
        tokens: list[str] = []
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            # Skip comment-only lines (RFC says # is not standard but common)
            if stripped.startswith("#"):
                i += 1
                continue
            # Walk tokens; if we hit `macdef`, swallow body until blank line
            line_tokens = stripped.split()
            j = 0
            macdef_started = False
            while j < len(line_tokens):
                tok = line_tokens[j]
                if tok == "macdef":
                    # macdef NAME — then body until blank line
                    tokens.append(tok)
                    if j + 1 < len(line_tokens):
                        tokens.append(line_tokens[j + 1])
                    macdef_started = True
                    break
                tokens.append(tok)
                j += 1
            i += 1
            if macdef_started:
                # Skip until blank line
                while i < len(lines) and lines[i].strip():
                    i += 1
                # Skip the blank line itself (and any empty-block separator)

        # Walk tokens, building blocks
        blocks: list[dict] = []
        current: dict | None = None
        idx = 0
        while idx < len(tokens):
            tok = tokens[idx]
            if tok in _BLOCK_KEYWORDS:
                if current is not None:
                    blocks.append(current)
                if tok == "machine":
                    if idx + 1 >= len(tokens):
                        result.warnings.append("`machine` keyword with no hostname, skipping")
                        current = None
                        idx += 1
                        continue
                    current = {"machine": tokens[idx + 1], "is_default": False}
                    idx += 2
                else:  # default
                    current = {"machine": "default", "is_default": True}
                    idx += 1
                continue
            if current is None:
                # stray token before any machine/default — skip
                idx += 1
                continue
            if tok in ("login", "password", "account"):
                if idx + 1 >= len(tokens):
                    result.warnings.append(f"`{tok}` keyword with no value, skipping")
                    idx += 1
                    continue
                current[tok] = tokens[idx + 1]
                idx += 2
                continue
            if tok == "macdef":
                # macdef NAME — body already swallowed in tokenizer, but we still
                # have macdef + name in the token stream
                idx += 2
                continue
            # Unknown token — likely a continuation or stray; skip
            idx += 1
        if current is not None:
            blocks.append(current)

        creds_found = 0
        for block in blocks:
            machine = block.get("machine", "default")
            login = block.get("login")
            password = block.get("password")
            if password is None:
                # No password — nothing to harvest
                continue
            name = f"netrc:{machine}:{login}" if login else f"netrc:{machine}"
            result.credentials_found.append(
                CredentialData(
                    cred_type="password",
                    value=password,
                    username=login,
                    relationship_type="found_on_disk",
                    name=name,
                )
            )
            creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
