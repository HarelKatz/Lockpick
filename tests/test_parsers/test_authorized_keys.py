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


# ─── Options capture (quote-aware) ────────────────────────────────────────────

def test_no_options_leaves_key_options_none(metadata):
    content = b"ssh-rsa AAAAB3NzABC... plain@host\n"
    result = AuthorizedKeysParser().parse(content, metadata)
    assert result.credentials_found[0].key_options is None
    assert result.credentials_found[0].value == "ssh-rsa AAAAB3NzABC... plain@host"


def test_options_captured_verbatim(metadata):
    content = b"no-port-forwarding,no-pty ssh-rsa AAAAB3NzABC... restricted-key\n"
    result = AuthorizedKeysParser().parse(content, metadata)
    assert result.credentials_found[0].key_options == "no-port-forwarding,no-pty"


def test_quoted_option_value_containing_a_key_type_does_not_truncate(metadata):
    """A key type inside a quoted option value must not be mistaken for the real key.

    The old whitespace token walk stopped at the first token *equal to* a known key
    type, so the `ssh-rsa` inside command="..." split the line in the wrong place —
    storing 'ssh-rsa denied" ssh-rsa …' as the key material.
    """
    content = b'command="echo ssh-rsa denied" ssh-rsa AAAAB3NzaC1yc2E user@host\n'
    result = AuthorizedKeysParser().parse(content, metadata)
    assert len(result.credentials_found) == 1
    cred = result.credentials_found[0]
    assert cred.value == "ssh-rsa AAAAB3NzaC1yc2E user@host"
    assert cred.key_options == 'command="echo ssh-rsa denied"'


def test_escaped_quotes_and_separators_inside_option_value(metadata):
    """Real-world hostile case (cado sample): escaped quotes, semicolons, spaces."""
    content = (
        b'no-port-forwarding,command="echo \\"login as ec2-user\\";sleep 10" '
        b"ssh-rsa AAAAB3NzaC1yc2E attacker@kali\n"
    )
    result = AuthorizedKeysParser().parse(content, metadata)
    assert len(result.credentials_found) == 1
    cred = result.credentials_found[0]
    assert cred.value == "ssh-rsa AAAAB3NzaC1yc2E attacker@kali"
    assert cred.key_options == 'no-port-forwarding,command="echo \\"login as ec2-user\\";sleep 10"'


def test_from_acl_is_captured_verbatim(metadata):
    """from= rides along in key_options; turning it into edges is a later phase."""
    content = b'from="10.0.0.5,!jump.corp.net" ssh-ed25519 AAAAC3NzaC1lZDI1 ops@bastion\n'
    result = AuthorizedKeysParser().parse(content, metadata)
    cred = result.credentials_found[0]
    assert cred.value == "ssh-ed25519 AAAAC3NzaC1lZDI1 ops@bastion"
    assert cred.key_options == 'from="10.0.0.5,!jump.corp.net"'
