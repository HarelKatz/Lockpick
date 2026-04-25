"""Parser for `env` / `printenv` output — aggressive secret harvest.

Each KEY=VALUE line whose key matches a known secret pattern (`*_KEY`,
`*_TOKEN`, `*_PASSWORD`, `*_SECRET`, `AWS_*`, `*_DSN`, `DATABASE_URL`)
becomes a CredentialData.  Common harmless keys (PATH, LANG, etc.) are
hard-skipped so we don't spam the credential store.

Multi-line values (rare but legal — e.g. a key with embedded newlines)
are collapsed to the first line — env exporters that produce multi-line
output usually wrap the second line of context, but we err on the side of
ignoring continuation lines to avoid garbage.
"""
from __future__ import annotations

import gzip
import re

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata

# Hard-deny exact keys.  These are noise even if they match the suffix patterns.
_DENY_EXACT = {
    "PATH", "HOME", "LANG", "LANGUAGE", "TERM", "SHELL", "PWD", "OLDPWD",
    "LOGNAME", "USER", "SHLVL", "MAIL", "DISPLAY", "TZ", "_",
    "TMPDIR", "TMP", "TEMP", "TERM_PROGRAM", "TERM_PROGRAM_VERSION",
    "TERM_SESSION_ID", "COLORTERM", "EDITOR", "PAGER", "LESS", "LESSCLOSE",
    "LESSOPEN", "JC_COLORS", "JELLO_COLORS", "PYENV_SHELL", "PYENV_ROOT",
    "LS_COLORS", "MANPATH", "INFOPATH",
    # SSH session metadata — not secrets
    "SSH_CLIENT", "SSH_CONNECTION", "SSH_TTY", "SSH_AUTH_SOCK",
    "GPG_TTY", "WINDOWID",
}
# Hard-deny prefixes
_DENY_PREFIX = ("LD_", "XDG_", "GTK_", "QT_", "GDK_", "G_", "DBUS_", "GNOME_",
                "KDE_", "LC_", "DESKTOP_", "GIO_", "GSETTINGS_")

# Suffix patterns that signal a secret value.
_SUFFIX_RE = re.compile(
    r"(?:^|_)(?:"
    r"KEY|TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|ACCESS_KEY|"
    r"SECRET_KEY|DSN|AUTH|CREDENTIALS|APIKEY|PASS"
    r")$",
    re.IGNORECASE,
)
# Exact-name secret keys that don't end with a suffix.
_EXACT_SECRETS = {
    "DATABASE_URL", "DB_URL", "REDIS_URL", "MONGO_URL",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "GOOGLE_API_KEY", "GCP_TOKEN",
    "GITHUB_TOKEN", "GITLAB_TOKEN", "DOCKER_PASSWORD",
}


def _is_secret_key(key: str) -> bool:
    if key in _DENY_EXACT:
        return False
    for p in _DENY_PREFIX:
        if key.startswith(p):
            return False
    if key in _EXACT_SECRETS:
        return True
    if _SUFFIX_RE.search(key):
        return True
    # `*_URL` carrying credentials — only flag DATABASE_URL / *_DSN style names,
    # not generic `URL` or `WEBSITE_URL`.  The exact set above covers the
    # common cases.
    return False


class EnvOutputParser(BaseParser):
    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        if content[:2] == b"\x1f\x8b":
            try:
                content = gzip.decompress(content)
            except Exception as e:
                result.warnings.append(f"Failed to decompress gzip: {e}")
                return result

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        username = metadata.username
        creds = 0
        seen: set[tuple[str, str]] = set()
        for raw_line in text.splitlines():
            if not raw_line or "=" not in raw_line:
                continue
            # Skip lines that don't start with a valid key character — these
            # are continuation lines from multi-line variables.
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", raw_line):
                continue
            key, _, value = raw_line.partition("=")
            if not _is_secret_key(key):
                continue
            value = value.strip()
            if not value:
                continue
            sig = (key, value)
            if sig in seen:
                continue
            seen.add(sig)
            result.credentials_found.append(CredentialData(
                cred_type="password",
                value=value,
                name=key,
                username=username,
                relationship_type="found_on_disk",
            ))
            creds += 1

        result.stats = {"credentials": creds}
        return result
