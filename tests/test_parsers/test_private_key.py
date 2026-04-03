"""Tests for private key parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.private_key import PrivateKeyParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="private_key",
        username="alice",
        filename="id_rsa",
    )


def test_parses_rsa_key(metadata):
    content = (FIXTURES / "id_rsa").read_bytes()
    result = PrivateKeyParser().parse(content, metadata)
    assert len(result.credentials_found) == 1
    cred = result.credentials_found[0]
    assert cred.cred_type == "private_key"
    assert cred.relationship_type == "found_on_disk"
    assert cred.username == "alice"


def test_fingerprint_computed(metadata):
    content = (FIXTURES / "id_rsa").read_bytes()
    result = PrivateKeyParser().parse(content, metadata)
    assert "fingerprint" in result.stats
    assert result.stats["fingerprint"].startswith("SHA256:")


def test_key_type_in_stats(metadata):
    content = (FIXTURES / "id_rsa").read_bytes()
    result = PrivateKeyParser().parse(content, metadata)
    assert result.stats.get("key_type") == "ssh-rsa"


def test_host_user_recorded(metadata):
    content = (FIXTURES / "id_rsa").read_bytes()
    result = PrivateKeyParser().parse(content, metadata)
    assert any(u[0] == "alice" for u in result.host_users_found)


def test_non_key_file(metadata):
    result = PrivateKeyParser().parse(b"this is not a key\n", metadata)
    assert result.credentials_found == []
    assert len(result.warnings) > 0
