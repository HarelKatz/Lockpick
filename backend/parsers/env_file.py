"""Parser for `.env` files.

Aggressive harvest of secret-shaped keys. Format:
    # comment
    [export ]KEY=value
    [export ]KEY="value with spaces"
    [export ]KEY='value'
    KEY=

We emit a CredentialData for any key whose name matches a secret-shaped
pattern AND whose value is non-empty.
"""
from __future__ import annotations

import re

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata

# Suffixes that indicate the value is a secret. Matched case-insensitively
# at the end of the key (e.g. `MY_API_TOKEN`, `STRIPE_SECRET_KEY`).
_SECRET_SUFFIXES = (
    "_KEY",
    "_TOKEN",
    "_PASSWORD",
    "_PASS",
    "_PWD",
    "_SECRET",
    "_API_KEY",
    "_DSN",
)

# Exact key names we always treat as secret
_SECRET_EXACT = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "DATABASE_URL",
    "DB_URL",
    "REDIS_URL",
    "MONGODB_URI",
    "MONGO_URL",
    "POSTGRES_URL",
    "MYSQL_URL",
}

# Prefixes that indicate the whole namespace is sensitive
_SECRET_PREFIXES = (
    "STRIPE_",
    "SENDGRID_",
    "MAILGUN_",
    "TWILIO_",
    "GITHUB_TOKEN",
    "GITLAB_TOKEN",
)

# `KEY=value` or `KEY="value"` or `KEY='value'`, optional `export ` prefix
_LINE_RE = re.compile(
    r"""
    ^\s*
    (?:export\s+)?
    (?P<key>[A-Za-z_][A-Za-z0-9_.]*)
    \s*=\s*
    (?P<value>.*?)
    \s*$
    """,
    re.VERBOSE,
)


def _is_secret_key(key: str) -> bool:
    upper = key.upper()
    if upper in _SECRET_EXACT:
        return True
    if any(upper.endswith(suf) for suf in _SECRET_SUFFIXES):
        return True
    if any(upper.startswith(pre) for pre in _SECRET_PREFIXES):
        return True
    return False


def _strip_value(raw: str) -> str:
    """Strip optional surrounding quotes; respect inline `#` comments only when unquoted."""
    if not raw:
        return raw
    s = raw
    # Quoted forms
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    # Unquoted: strip inline `# comment` (loose — only when ` #` appears)
    hash_idx = s.find(" #")
    if hash_idx >= 0:
        s = s[:hash_idx].rstrip()
    return s


class EnvFileParser(BaseParser):
    """Parses `.env` files and aggressively harvests secret-named values."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        creds_found = 0
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = _LINE_RE.match(raw_line)
            if not m:
                continue
            key = m.group("key")
            value = _strip_value(m.group("value"))
            if not value:
                continue
            if not _is_secret_key(key):
                continue

            result.credentials_found.append(
                CredentialData(
                    cred_type="password",
                    value=value,
                    username=None,
                    relationship_type="found_on_disk",
                    name=f"env:{key}",
                )
            )
            creds_found += 1

        result.stats = {"credentials": creds_found}
        return result
