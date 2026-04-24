"""Tests for authorized_keys parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.authorized_keys import AuthorizedKeysParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="authorized_keys",
        username="alice",
        filename="authorized_keys",
    )


def test_parses_valid_keys(metadata):
    content = (FIXTURES / "authorized_keys").read_bytes()
    result = AuthorizedKeysParser().parse(content, metadata)
    assert len(result.credentials_found) == 3
    for cred in result.credentials_found:
        assert cred.cred_type == "public_key"
        assert cred.relationship_type == "authorized_key"
        assert cred.username == "alice"


def test_records_host_user(metadata):
    content = (FIXTURES / "authorized_keys").read_bytes()
    result = AuthorizedKeysParser().parse(content, metadata)
    assert any(u[0] == "alice" for u in result.host_users_found)


def test_stats_populated(metadata):
    content = (FIXTURES / "authorized_keys").read_bytes()
    result = AuthorizedKeysParser().parse(content, metadata)
    assert result.stats["keys_parsed"] == 3


def test_empty_file(metadata):
    result = AuthorizedKeysParser().parse(b"", metadata)
    assert result.credentials_found == []
    assert result.stats["keys_parsed"] == 0


def test_only_comments(metadata):
    result = AuthorizedKeysParser().parse(b"# comment\n# another\n", metadata)
    assert result.credentials_found == []


def test_malformed_line_warns(metadata):
    result = AuthorizedKeysParser().parse(b"not-a-key\n", metadata)
    assert len(result.warnings) > 0


def test_option_prefix_value_is_canonical(metadata):
    """BUG-03 regression: option-prefix keys must store canonical key material, not the full line."""
    content = b"no-port-forwarding,no-pty ssh-rsa AAAAB3NzABC... restricted-key\n"
    result = AuthorizedKeysParser().parse(content, metadata)
    assert len(result.credentials_found) == 1
    assert result.credentials_found[0].value.startswith("ssh-rsa ")
    assert "no-port-forwarding" not in result.credentials_found[0].value
