"""Tests for RcloneConfigParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.rclone_config import RcloneConfigParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "rclone_config"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="rclone_config",
        filename="rclone.conf",
    )


def test_multi_remote(metadata):
    content = (FIXTURES / "multi_remote").read_bytes()
    result = RcloneConfigParser().parse(content, metadata)

    # s3-bucket: access_key_id, secret_access_key = 2
    # onedrive-personal: token = 1
    # ftp-server: pass = 1
    # crypt-volume: password, password2 = 2
    # Total: 6
    assert len(result.credentials_found) == 6
    assert result.stats == {"credentials": 6}

    by_name = {c.name: c for c in result.credentials_found}
    assert by_name["rclone:s3-bucket:access_key_id"].value == "AKIARCLONE"
    assert by_name["rclone:s3-bucket:secret_access_key"].value == "rclonesecret"
    assert "{" in by_name["rclone:onedrive-personal:token"].value
    assert by_name["rclone:ftp-server:pass"].value == "obscuredpass"
    assert by_name["rclone:crypt-volume:password"].value == "crypt_pass"
    assert by_name["rclone:crypt-volume:password2"].value == "crypt_salt"

    for c in result.credentials_found:
        assert c.cred_type == "password"
        assert c.relationship_type == "found_on_disk"


def test_section_without_secrets(metadata):
    content = b"""[local]
type = local
nounc = true
"""
    result = RcloneConfigParser().parse(content, metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_empty_file(metadata):
    result = RcloneConfigParser().parse(b"", metadata)
    assert result.credentials_found == []


def test_garbage(metadata):
    result = RcloneConfigParser().parse(b"not\nvalid ini\n[\n", metadata)
    assert isinstance(result.credentials_found, list)
