"""Unit tests for the ps_output parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.ps_output import PsOutputParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ps_output"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="ps_output")


def test_extracts_ssh_and_scp_connections():
    """Fixture has one ssh row and one scp row → 2 ConnectionData."""
    content = (FIXTURES / "ps_aux.out").read_bytes()
    result = PsOutputParser().parse(content, _meta())
    conns = result.connections_found
    assert len(conns) == 2

    ssh_conn = next(c for c in conns if c.connection_type == "ssh")
    assert ssh_conn.dst_ip == "10.0.0.5"
    assert ssh_conn.dst_user == "root"
    assert ssh_conn.src_user == "alice"

    scp_conn = next(c for c in conns if c.connection_type == "scp")
    assert scp_conn.dst_ip == "webserver.corp"
    assert scp_conn.dst_user == "bob"


def test_kernel_threads_skipped():
    """Cmdline starting with `[kthreadd]` etc. should not produce any record."""
    content = (FIXTURES / "ps_aux.out").read_bytes()
    result = PsOutputParser().parse(content, _meta())
    # No connection or credential should reference `[kthreadd]`
    for c in result.connections_found:
        assert "kthreadd" not in (c.raw_line or "")
    for cred in result.credentials_found:
        assert "kthreadd" not in (cred.value or "")


def test_credential_harvest_from_cmdline():
    """mysql -p, curl -u, postgres URL → 3 CredentialData."""
    content = (FIXTURES / "ps_aux.out").read_bytes()
    result = PsOutputParser().parse(content, _meta())
    creds = result.credentials_found
    # Expect exactly 3: mysql_password, curl_basic_auth, postgresql_url
    assert len(creds) == 3

    by_name = {c.name: c for c in creds}
    assert "mysql_password" in by_name
    assert by_name["mysql_password"].value == "supersecret123"
    assert by_name["curl_basic_auth"].value == "admin:hunter2"
    assert "postgresql_url" in by_name or "postgres_url" in by_name


def test_credential_username_from_ps_user_column():
    """`bob`'s mysql cmdline should produce a CredentialData with username=bob."""
    content = (FIXTURES / "ps_aux.out").read_bytes()
    result = PsOutputParser().parse(content, _meta())
    mysql_cred = next(c for c in result.credentials_found if c.name == "mysql_password")
    assert mysql_cred.username == "bob"


def test_stats_counts():
    content = (FIXTURES / "ps_aux.out").read_bytes()
    result = PsOutputParser().parse(content, _meta())
    assert result.stats == {"connections": 2, "credentials": 3}


def test_empty_file():
    result = PsOutputParser().parse(b"", _meta())
    assert result.connections_found == []
    assert result.credentials_found == []
    assert result.stats == {"connections": 0, "credentials": 0}
