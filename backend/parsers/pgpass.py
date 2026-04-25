r"""Parser for ~/.pgpass (PostgreSQL password file).

Format: hostname:port:database:username:password
        - `*` is a wildcard for any field.
        - `\:` and `\\` are escapes for literal `:` and `\`.
        - Lines starting with `#` are comments.
"""
from __future__ import annotations

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata


def _split_pgpass_line(line: str) -> list[str]:
    """Split a pgpass line on `:` honouring `\\:` and `\\\\` escapes."""
    fields: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            buf.append(line[i + 1])
            i += 2
            continue
        if ch == ":":
            fields.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    fields.append("".join(buf))
    return fields


class PgpassParser(BaseParser):
    """Parses ~/.pgpass — emits one password CredentialData per non-comment line."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        creds_found = 0
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            fields = _split_pgpass_line(line)
            if len(fields) < 5:
                result.warnings.append(
                    f"Line {lineno}: expected 5 fields, got {len(fields)}, skipping"
                )
                continue

            # Standard pgpass: 5 fields. Some tools (e.g. PGAdmin/aliased forms)
            # prepend an alias making it 6+. Use the LAST 5 as the canonical.
            if len(fields) > 5:
                fields = fields[-5:]

            hostname, port, database, username, password = (
                fields[0], fields[1], fields[2], fields[3], fields[4]
            )

            if not password:
                result.warnings.append(f"Line {lineno}: empty password, skipping")
                continue

            name = f"pgpass:{hostname}:{database}"
            result.credentials_found.append(
                CredentialData(
                    cred_type="password",
                    value=password,
                    username=username if username else None,
                    relationship_type="found_on_disk",
                    name=name,
                )
            )
            creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
