"""
Parametrised robustness tests: every parser must survive every bad/corrupt input
without raising an exception, and must always return a valid ParseResult.

Requires tests/fixtures/bad/ to exist.
Run `uv run --project backend tests/generate_fixtures.py` first if needed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import ParseResult, UploadMetadata
from parsers.auth_log import AuthLogParser
from parsers.authorized_keys import AuthorizedKeysParser
from parsers.bash_history import BashHistoryParser
from parsers.known_hosts import KnownHostsParser
from parsers.nmap_xml import NmapXmlParser
from parsers.passwd import PasswdParser
from parsers.private_key import PrivateKeyParser
from parsers.shadow import ShadowParser
from parsers.ssh_config import SshConfigParser
from parsers.sshd_config import SshdConfigParser
from parsers.wtmp import WtmpParser

BAD = Path(__file__).parent.parent / "fixtures" / "bad"

pytestmark = pytest.mark.skipif(
    not BAD.exists(),
    reason="Bad fixtures not generated — run tests/generate_fixtures.py first",
)

# All bad fixture files
BAD_FILES = list(BAD.iterdir()) if BAD.exists() else []

# All parsers with a representative file_type and optional username
PARSERS = [
    ("auth_log",        AuthLogParser,        None),
    ("authorized_keys", AuthorizedKeysParser, "testuser"),
    ("bash_history",    BashHistoryParser,    "testuser"),
    ("known_hosts",     KnownHostsParser,     "testuser"),
    ("nmap_xml",        NmapXmlParser,        None),
    ("passwd",          PasswdParser,         None),
    ("private_key",     PrivateKeyParser,     "testuser"),
    ("shadow",          ShadowParser,         None),
    ("ssh_config",      SshConfigParser,      "testuser"),
    ("sshd_config",     SshdConfigParser,     None),
    ("wtmp",            WtmpParser,           None),
]


def _metadata(file_type: str, username: str | None) -> UploadMetadata:
    return UploadMetadata(
        op_id="op-test",
        host_id="host-test",
        file_type=file_type,
        username=username,
        filename="bad_input",
    )


@pytest.mark.parametrize("bad_file", BAD_FILES, ids=[f.name for f in BAD_FILES])
@pytest.mark.parametrize(
    "file_type,parser_cls,username",
    PARSERS,
    ids=[p[0] for p in PARSERS],
)
def test_parser_never_raises(file_type, parser_cls, username, bad_file):
    """Every parser must not raise for any bad input — it should return a ParseResult."""
    content = bad_file.read_bytes()
    meta = _metadata(file_type, username)
    parser = parser_cls()

    # Must not raise
    result = parser.parse(content, meta)

    # Must return a ParseResult
    assert isinstance(result, ParseResult), (
        f"{parser_cls.__name__} returned {type(result)} instead of ParseResult"
    )

    # Warnings/results may be empty, but fields must be lists
    assert isinstance(result.warnings, list)
    assert isinstance(result.credentials_found, list)
    assert isinstance(result.connections_found, list)
    assert isinstance(result.hosts_found, list)


# ─── Targeted behaviour tests for specific bad fixtures ───────────────────────

def test_auth_log_no_sshd_lines_produces_zero_connections():
    """no_sshd.log has kernel/cron lines but no sshd entries — zero connections expected."""
    path = BAD / "no_sshd.log"
    if not path.exists():
        pytest.skip("no_sshd.log fixture not present")
    meta = _metadata("auth_log", None)
    result = AuthLogParser().parse(path.read_bytes(), meta)
    assert result.connections_found == [], (
        f"Expected 0 connections from non-sshd log, got {len(result.connections_found)}"
    )
