"""Tests for DockerConfigParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.docker_config import DockerConfigParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "docker_config"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="docker_config",
        filename="config.json",
    )


def test_with_auths(metadata):
    content = (FIXTURES / "with_auths.json").read_bytes()
    result = DockerConfigParser().parse(content, metadata)

    # Two `auth` entries (alice, bob) plus one split user/password (carol) = 3.
    assert len(result.credentials_found) == 3
    assert result.stats == {"credentials": 3}

    by_name = {c.name: c for c in result.credentials_found}
    assert "docker:registry.example.com" in by_name
    assert by_name["docker:registry.example.com"].value == "s3cret"
    assert by_name["docker:registry.example.com"].username == "alice"

    # snowman in password
    assert "docker:https://index.docker.io/v1/" in by_name
    assert by_name["docker:https://index.docker.io/v1/"].username == "bob"

    assert "docker:split.example.com" in by_name
    assert by_name["docker:split.example.com"].value == "carolpw"
    assert by_name["docker:split.example.com"].username == "carol"

    for c in result.credentials_found:
        assert c.cred_type == "password"
        assert c.relationship_type == "found_on_disk"


def test_credstore_only(metadata):
    content = (FIXTURES / "credstore_only.json").read_bytes()
    result = DockerConfigParser().parse(content, metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_invalid_json(metadata):
    result = DockerConfigParser().parse(b"{bad json", metadata)
    assert result.credentials_found == []
    assert any("Invalid JSON" in w for w in result.warnings)


def test_empty_file(metadata):
    result = DockerConfigParser().parse(b"", metadata)
    assert result.credentials_found == []


def test_undecodable_auth(metadata):
    content = b'{"auths": {"r.example.com": {"auth": "this-has-no-colon"}}}'
    result = DockerConfigParser().parse(content, metadata)
    assert result.credentials_found == []
    assert any("could not decode" in w for w in result.warnings)


def test_top_level_array_warning(metadata):
    result = DockerConfigParser().parse(b"[]", metadata)
    assert result.credentials_found == []
    assert any("Expected JSON object" in w for w in result.warnings)
