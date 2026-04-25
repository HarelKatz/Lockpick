"""Tests for AwsCredentialsParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.aws_credentials import AwsCredentialsParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "aws_credentials"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="aws_credentials",
        filename="credentials",
    )


def test_two_profiles(metadata):
    content = (FIXTURES / "two_profiles").read_bytes()
    result = AwsCredentialsParser().parse(content, metadata)

    # default has 2 secrets, prod has 3 → 5 total
    assert len(result.credentials_found) == 5
    assert result.stats == {"credentials": 5}

    by_name = {c.name: c for c in result.credentials_found}
    assert by_name["aws:default:aws_access_key_id"].value == "AKIADEFAULT"
    assert by_name["aws:default:aws_secret_access_key"].value == "defaultsecret"
    assert by_name["aws:prod:aws_access_key_id"].value == "AKIAPROD"
    assert by_name["aws:prod:aws_secret_access_key"].value == "prodsecret"
    assert by_name["aws:prod:aws_session_token"].value == "prodtoken"

    for c in result.credentials_found:
        assert c.cred_type == "password"
        assert c.relationship_type == "found_on_disk"
        assert c.username is None


def test_empty_section(metadata):
    content = b"[default]\n# nothing here\n"
    result = AwsCredentialsParser().parse(content, metadata)
    assert result.credentials_found == []


def test_empty_file(metadata):
    result = AwsCredentialsParser().parse(b"", metadata)
    assert result.credentials_found == []


def test_garbage(metadata):
    result = AwsCredentialsParser().parse(b"][\n", metadata)
    assert isinstance(result.credentials_found, list)
