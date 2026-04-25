"""Tests for EnvFileParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.env_file import EnvFileParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "env_file"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="env_file",
        filename=".env",
    )


def test_typical_env(metadata):
    content = (FIXTURES / "typical_env").read_bytes()
    result = EnvFileParser().parse(content, metadata)

    # Expected secrets:
    #   DATABASE_URL, REDIS_URL, NEXTAUTH_SECRET, GITHUB_CLIENT_SECRET,
    #   STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, AWS_ACCESS_KEY_ID,
    #   AWS_SECRET_ACCESS_KEY, SENTRY_DSN
    # = 9 credentials.
    # NOT secrets (skipped): APP_NAME, PORT, GITHUB_CLIENT_ID (not secret-suffixed),
    # SESSION_PASSWORD (empty value), LOG_LEVEL (not secret).
    assert len(result.credentials_found) == 9
    assert result.stats == {"credentials": 9}

    by_name = {c.name: c for c in result.credentials_found}
    assert by_name["env:DATABASE_URL"].value == "postgres://user:pass@db.example.com:5432/app"
    assert by_name["env:REDIS_URL"].value == "redis://redis.example.com:6379"
    assert by_name["env:NEXTAUTH_SECRET"].value == "topsecret"  # quotes stripped
    assert by_name["env:STRIPE_SECRET_KEY"].value == "sk_live_abcdef"
    assert by_name["env:STRIPE_WEBHOOK_SECRET"].value == "whsec_xyz"
    assert by_name["env:AWS_ACCESS_KEY_ID"].value == "AKIAEXAMPLE"
    assert by_name["env:AWS_SECRET_ACCESS_KEY"].value == "secretsauce"
    assert by_name["env:SENTRY_DSN"].value == "https://abc@sentry.io/1"

    for c in result.credentials_found:
        assert c.cred_type == "password"
        assert c.relationship_type == "found_on_disk"
        assert c.username is None


def test_non_secret_keys_ignored(metadata):
    content = b"APP_NAME=app\nPORT=3000\n"
    result = EnvFileParser().parse(content, metadata)
    assert result.credentials_found == []


def test_empty_value_ignored(metadata):
    content = b"API_KEY=\nTOKEN=\n"
    result = EnvFileParser().parse(content, metadata)
    assert result.credentials_found == []


def test_quoted_value_stripped(metadata):
    content = b'API_KEY="quoted_secret"\n'
    result = EnvFileParser().parse(content, metadata)
    assert len(result.credentials_found) == 1
    assert result.credentials_found[0].value == "quoted_secret"


def test_export_prefix(metadata):
    content = b"export API_KEY=exported_secret\n"
    result = EnvFileParser().parse(content, metadata)
    assert len(result.credentials_found) == 1
    assert result.credentials_found[0].value == "exported_secret"


def test_empty_file(metadata):
    result = EnvFileParser().parse(b"", metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_garbage(metadata):
    result = EnvFileParser().parse(b"\x00\x01\x02 garbage\n", metadata)
    assert isinstance(result.credentials_found, list)
