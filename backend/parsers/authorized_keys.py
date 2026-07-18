"""Parser for .ssh/authorized_keys files."""
from __future__ import annotations

from parsers import (
    BaseParser,
    ConnectionData,
    CredentialData,
    ParseResult,
    SshConfigPatternData,
    UploadMetadata,
)

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


def _split_outside_quotes(s: str, sep: str) -> list[str]:
    """Split on `sep`, ignoring separators inside double quotes."""
    out: list[str] = []
    buf: list[str] = []
    in_quote = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and in_quote and i + 1 < len(s):
            buf.append(s[i:i + 2])
            i += 2
            continue
        if c == '"':
            in_quote = not in_quote
            buf.append(c)
        elif c == sep and not in_quote:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(c)
        i += 1
    out.append("".join(buf))
    return out


def _from_acl_entries(options: str) -> list[str]:
    """Return the comma-separated entries of a `from="…"` option, or []."""
    for opt in _split_outside_quotes(options, ","):
        opt = opt.strip()
        if not opt.lower().startswith("from="):
            continue
        value = opt[len("from="):].strip()
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        value = value.replace('\\"', '"')
        return [e.strip() for e in value.split(",") if e.strip()]
    return []


def _is_literal_acl_entry(entry: str) -> bool:
    """True for a single concrete host — not a negation, glob, or CIDR.

    Negations (`!host`) are exclusions, globs and CIDRs match a set rather than one
    host; all three are standing rules resolved elsewhere, not one-shot edges.
    """
    return not (entry.startswith("!") or "*" in entry or "?" in entry or "/" in entry)


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
        acl_edges = 0
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

            # A `from=` ACL is the destination host asserting which sources may use
            # this key — an inbound grant, so the upload host is the destination.
            # Only concrete single hosts become edges here; globs/CIDRs are standing
            # rules handled separately. Confidence is pinned to indicator by
            # parser_file_type (Architecture Rule #27), never `confirmed`.
            acl = _from_acl_entries(options or "")

            # Globs/CIDRs match a SET of hosts, including hosts not discovered yet, so
            # they become standing rules rather than one-shot edges. Negations ride
            # along so exclusions still apply. A rule with no positive entry (e.g.
            # from="10.0.0.5,!jump") would match nothing — don't store it.
            rule_entries = [e for e in acl if not _is_literal_acl_entry(e)]
            if any(not e.startswith("!") for e in rule_entries):
                result.patterns_found.append(
                    SshConfigPatternData(aliases=rule_entries, username=username)
                )

            for entry in acl:
                if not _is_literal_acl_entry(entry):
                    continue
                result.connections_found.append(
                    ConnectionData(
                        src_ip=entry,
                        dst_ip="__upload_host__",
                        connection_type="ssh",
                        direction_context="from_dst_logs",
                        dst_user=username,
                        auth_method="publickey",
                        raw_line=line[:512],
                    )
                )
                acl_edges += 1

        if username:
            # Record that this user account exists on the host
            result.host_users_found.append((username, None, None))

        result.stats = {"keys_parsed": keys_found, "from_acl_edges": acl_edges}
        return result
