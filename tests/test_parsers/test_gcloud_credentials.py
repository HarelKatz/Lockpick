"""Tests for GcloudCredentialsParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.gcloud_credentials import GcloudCredentialsParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "gcloud_credentials"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="gcloud_credentials",
        filename="application_default_credentials.json",
    )


def test_authorized_user(metadata):
    content = (FIXTURES / "authorized_user.json").read_bytes()
    result = GcloudCredentialsParser().parse(content, metadata)

    # Authorized-user JSON: refresh_token + client_secret = 2 credentials
    assert len(result.credentials_found) == 2
    assert result.stats == {"credentials": 2}

    by_name = {c.name: c for c in result.credentials_found}
    assert "gcp:refresh_token:client-abc.apps.googleusercontent.com" in by_name
    assert by_name["gcp:refresh_token:client-abc.apps.googleusercontent.com"].value == "1//refreshtoken_value"
    assert by_name["gcp:refresh_token:client-abc.apps.googleusercontent.com"].cred_type == "password"

    assert "gcp:client_secret:client-abc.apps.googleusercontent.com" in by_name
    assert by_name["gcp:client_secret:client-abc.apps.googleusercontent.com"].value == "GOCSPX-clientsecret"

    for c in result.credentials_found:
        assert c.relationship_type == "found_on_disk"
        assert c.username is None


def test_service_account(metadata):
    content = (FIXTURES / "service_account.json").read_bytes()
    result = GcloudCredentialsParser().parse(content, metadata)

    assert len(result.credentials_found) == 1
    cred = result.credentials_found[0]
    assert cred.cred_type == "private_key"
    assert cred.name == "gcp:service_account:svc@my-project.iam.gserviceaccount.com"
    assert "BEGIN PRIVATE KEY" in cred.value
    assert cred.relationship_type == "found_on_disk"


def test_service_account_missing_key(metadata):
    content = b'{"type": "service_account", "client_email": "x@y.com"}'
    result = GcloudCredentialsParser().parse(content, metadata)
    assert result.credentials_found == []
    assert any("missing" in w for w in result.warnings)


def test_invalid_json(metadata):
    content = b"{not valid json"
    result = GcloudCredentialsParser().parse(content, metadata)
    assert result.credentials_found == []
    assert any("Invalid JSON" in w for w in result.warnings)


def test_empty_file(metadata):
    result = GcloudCredentialsParser().parse(b"", metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_top_level_array(metadata):
    content = b"[]"
    result = GcloudCredentialsParser().parse(content, metadata)
    assert result.credentials_found == []
    assert any("Expected JSON object" in w for w in result.warnings)
