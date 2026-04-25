"""Tests for GitCredentialsParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.git_credentials import GitCredentialsParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "git_credentials"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="git_credentials",
        filename=".git-credentials",
    )


def test_basic(metadata):
    content = (FIXTURES / "basic").read_bytes()
    result = GitCredentialsParser().parse(content, metadata)

    assert len(result.credentials_found) == 3
    assert result.stats == {"credentials": 3}

    by_name = {c.name: c for c in result.credentials_found}
    assert "git:github.com" in by_name
    assert by_name["git:github.com"].value == "s3cret"
    assert by_name["git:github.com"].username == "alice"

    assert "git:gitlab.com" in by_name
    # Percent-encoded value: %40 → @, %3A → :
    assert by_name["git:gitlab.com"].value == "p@ss:word"
    assert by_name["git:gitlab.com"].username == "bob"

    assert "git:code.example.com" in by_name
    assert by_name["git:code.example.com"].value == "ghp_token123"
    assert by_name["git:code.example.com"].username == "oauth2"

    for c in result.credentials_found:
        assert c.cred_type == "password"
        assert c.relationship_type == "found_on_disk"


def test_no_password_skipped(metadata):
    content = b"https://user@github.com\n"
    result = GitCredentialsParser().parse(content, metadata)
    assert result.credentials_found == []
    assert any("no password" in w for w in result.warnings)


def test_invalid_line_skipped(metadata):
    content = b"this is not a url\n"
    result = GitCredentialsParser().parse(content, metadata)
    assert result.credentials_found == []
    assert any("not a valid URL" in w for w in result.warnings)


def test_comments_and_blank(metadata):
    content = b"# header\n\nhttps://u:p@example.com\n"
    result = GitCredentialsParser().parse(content, metadata)
    assert len(result.credentials_found) == 1


def test_empty_file(metadata):
    result = GitCredentialsParser().parse(b"", metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}
