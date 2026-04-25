"""Tests for MysqlConfigParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.mysql_config import MysqlConfigParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mysql_config"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="mysql_config",
        filename=".my.cnf",
    )


def test_with_password(metadata):
    content = (FIXTURES / "with_password").read_bytes()
    result = MysqlConfigParser().parse(content, metadata)

    assert len(result.credentials_found) == 2
    assert result.stats == {"credentials": 2}

    by_name = {c.name: c for c in result.credentials_found}
    # client section has host → name uses host
    assert "mysql:db.example.com" in by_name
    assert by_name["mysql:db.example.com"].value == "s3cr3tpw"
    assert by_name["mysql:db.example.com"].username == "appuser"
    assert by_name["mysql:db.example.com"].cred_type == "password"
    assert by_name["mysql:db.example.com"].relationship_type == "found_on_disk"

    # mysqldump section has no host → name falls back to section
    assert "mysql:mysqldump" in by_name
    assert by_name["mysql:mysqldump"].value == "backup#pass"  # quotes stripped
    assert by_name["mysql:mysqldump"].username == "backup"


def test_no_credentials(metadata):
    content = (FIXTURES / "no_credentials").read_bytes()
    result = MysqlConfigParser().parse(content, metadata)

    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_empty_password(metadata):
    content = b"[client]\nuser = foo\npassword =\n"
    result = MysqlConfigParser().parse(content, metadata)
    assert result.credentials_found == []


def test_empty_file(metadata):
    result = MysqlConfigParser().parse(b"", metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_garbage_does_not_crash(metadata):
    # malformed INI — must not raise
    result = MysqlConfigParser().parse(b"not\nan ini file\n=\n[unclosed", metadata)
    assert isinstance(result.credentials_found, list)
