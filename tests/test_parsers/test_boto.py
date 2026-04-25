"""Tests for BotoParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.boto import BotoParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "boto"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="boto",
        filename=".boto",
    )


def test_credentials_and_proxy(metadata):
    content = (FIXTURES / "credentials_and_proxy").read_bytes()
    result = BotoParser().parse(content, metadata)

    # Credentials section: 4 secrets (aws + gs).
    # Boto section: 1 (proxy_pass with proxy_user as username).
    assert len(result.credentials_found) == 5
    assert result.stats == {"credentials": 5}

    by_name = {c.name: c for c in result.credentials_found}
    assert by_name["boto:Credentials:aws_access_key_id"].value == "AKIABOTO"
    assert by_name["boto:Credentials:aws_secret_access_key"].value == "bsecret"
    assert by_name["boto:Credentials:gs_access_key_id"].value == "GSKEY"
    assert by_name["boto:Credentials:gs_secret_access_key"].value == "gssecret"
    proxy = by_name["boto:Boto:proxy_pass"]
    assert proxy.value == "pxysecret"
    assert proxy.username == "pxyuser"

    for c in result.credentials_found:
        assert c.cred_type == "password"
        assert c.relationship_type == "found_on_disk"


def test_empty_file(metadata):
    result = BotoParser().parse(b"", metadata)
    assert result.credentials_found == []


def test_section_with_no_secrets(metadata):
    content = b"[Boto]\ndebug = 0\nnum_retries = 10\n"
    result = BotoParser().parse(content, metadata)
    assert result.credentials_found == []
