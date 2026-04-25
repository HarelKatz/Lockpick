"""Tests for PgpassParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.pgpass import PgpassParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "pgpass"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="pgpass",
        filename=".pgpass",
    )


def test_basic_pgpass(metadata):
    content = (FIXTURES / "basic_pgpass").read_bytes()
    result = PgpassParser().parse(content, metadata)

    assert len(result.credentials_found) == 3
    assert result.stats == {"credentials": 3}

    by_name = {c.name: c for c in result.credentials_found}
    assert "pgpass:db1.example.com:postgres" in by_name
    assert by_name["pgpass:db1.example.com:postgres"].value == "supersecret"
    assert by_name["pgpass:db1.example.com:postgres"].username == "dbadmin"
    assert by_name["pgpass:db1.example.com:postgres"].cred_type == "password"
    assert by_name["pgpass:db1.example.com:postgres"].relationship_type == "found_on_disk"

    assert "pgpass:*:appdb" in by_name
    assert by_name["pgpass:*:appdb"].value == "apppass"
    assert by_name["pgpass:*:appdb"].username == "appuser"

    assert "pgpass:db2:*" in by_name
    assert by_name["pgpass:db2:*"].value == "r3adon1y"


def test_escaped_chars(metadata):
    content = (FIXTURES / "escaped_pgpass").read_bytes()
    result = PgpassParser().parse(content, metadata)

    assert len(result.credentials_found) == 1
    cred = result.credentials_found[0]
    # database `weird\:db` → `weird:db` (escape unescaped)
    assert cred.name == "pgpass:db.example.com:weird:db"
    # password `pa\:ss\\word` → `pa:ss\word`
    assert cred.value == "pa:ss\\word"


def test_too_few_fields(metadata):
    content = b"only:three:fields\n"
    result = PgpassParser().parse(content, metadata)
    assert result.credentials_found == []
    assert len(result.warnings) == 1


def test_empty_password(metadata):
    content = b"host:5432:db:user:\n"
    result = PgpassParser().parse(content, metadata)
    assert result.credentials_found == []
    assert any("empty password" in w for w in result.warnings)


def test_comments_and_blank_lines(metadata):
    content = b"# header comment\n\n# another\nhost:5432:db:user:pw\n"
    result = PgpassParser().parse(content, metadata)
    assert len(result.credentials_found) == 1


def test_empty_file(metadata):
    result = PgpassParser().parse(b"", metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}
