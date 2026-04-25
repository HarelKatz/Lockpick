"""Tests for NetrcParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.netrc import NetrcParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "netrc"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="netrc",
        filename=".netrc",
    )


def test_basic_netrc_three_blocks(metadata):
    content = (FIXTURES / "basic_netrc").read_bytes()
    result = NetrcParser().parse(content, metadata)

    assert len(result.credentials_found) == 3
    assert result.stats == {"credentials": 3}

    by_machine = {c.name: c for c in result.credentials_found}
    assert "netrc:github.com:alice" in by_machine
    assert by_machine["netrc:github.com:alice"].value == "ghp_TopSecret123"
    assert by_machine["netrc:github.com:alice"].username == "alice"
    assert by_machine["netrc:github.com:alice"].cred_type == "password"
    assert by_machine["netrc:github.com:alice"].relationship_type == "found_on_disk"

    assert "netrc:api.example.com:bob" in by_machine
    assert by_machine["netrc:api.example.com:bob"].value == "pw2"

    assert "netrc:default:anonymous" in by_machine
    assert by_machine["netrc:default:anonymous"].value == "guest@example.com"


def test_macdef_body_is_skipped(metadata):
    content = (FIXTURES / "with_macdef").read_bytes()
    result = NetrcParser().parse(content, metadata)

    # Only two machine blocks have credentials; macdef body must not bleed in
    assert len(result.credentials_found) == 2
    by_machine = {c.name: c for c in result.credentials_found}
    assert "netrc:ftp.example.com:carol" in by_machine
    assert by_machine["netrc:ftp.example.com:carol"].value == "ftpsecret"
    assert "netrc:other.example.org:dave" in by_machine
    assert by_machine["netrc:other.example.org:dave"].value == "pw"


def test_block_without_password_skipped(metadata):
    content = b"machine no-pw.example.com login user\n"
    result = NetrcParser().parse(content, metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_empty_file(metadata):
    result = NetrcParser().parse(b"", metadata)
    assert result.credentials_found == []
    assert result.warnings == []
    assert result.stats == {"credentials": 0}


def test_garbage_does_not_crash(metadata):
    result = NetrcParser().parse(b"\x00\xff\x00 not a real netrc", metadata)
    # Should not crash; may produce nothing or warnings, but no exception
    assert isinstance(result.credentials_found, list)
