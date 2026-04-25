"""Tests for AwsConfigParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.aws_config import AwsConfigParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "aws_config"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="aws_config",
        filename="config",
    )


def test_no_secrets_emits_nothing(metadata):
    content = (FIXTURES / "no_secrets").read_bytes()
    result = AwsConfigParser().parse(content, metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_inline_session_token(metadata):
    content = (FIXTURES / "inline_session").read_bytes()
    result = AwsConfigParser().parse(content, metadata)

    assert len(result.credentials_found) == 3
    assert result.stats == {"credentials": 3}

    by_name = {c.name: c for c in result.credentials_found}
    # `[default]` is normalized to "default"
    assert "aws:default:aws_session_token" in by_name
    assert by_name["aws:default:aws_session_token"].value == "SESSION_TOKEN_VALUE"
    # `[profile dev]` strips the "profile " prefix
    assert "aws:dev:aws_access_key_id" in by_name
    assert by_name["aws:dev:aws_access_key_id"].value == "AKIAEXAMPLE"
    assert "aws:dev:aws_secret_access_key" in by_name
    assert by_name["aws:dev:aws_secret_access_key"].value == "SECRETSAUCE"

    for c in result.credentials_found:
        assert c.cred_type == "password"
        assert c.relationship_type == "found_on_disk"
        assert c.username is None


def test_empty_file(metadata):
    result = AwsConfigParser().parse(b"", metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_garbage_does_not_crash(metadata):
    result = AwsConfigParser().parse(b"\x00bad\nstuff\n[unclosed", metadata)
    assert isinstance(result.credentials_found, list)
