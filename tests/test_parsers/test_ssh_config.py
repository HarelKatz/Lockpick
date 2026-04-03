"""Tests for ssh_config parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.ssh_config import SshConfigParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="ssh_config",
        username="alice",
        filename="config",
    )


def test_parses_host_blocks(metadata):
    content = (FIXTURES / "ssh_config").read_bytes()
    result = SshConfigParser().parse(content, metadata)
    dst_ips = {c.dst_ip for c in result.connections_found}
    assert "10.10.0.1" in dst_ips
    assert "10.10.1.10" in dst_ips


def test_wildcard_block_skipped(metadata):
    content = (FIXTURES / "ssh_config").read_bytes()
    result = SshConfigParser().parse(content, metadata)
    dst_ips = {c.dst_ip for c in result.connections_found}
    # The Host * block has no Hostname and alias is *, should not produce a connection
    assert "*" not in dst_ips


def test_user_extracted(metadata):
    content = (FIXTURES / "ssh_config").read_bytes()
    result = SshConfigParser().parse(content, metadata)
    # jumpbox block has User admin
    jumpbox = next((c for c in result.connections_found if c.dst_ip == "10.10.0.1"), None)
    assert jumpbox is not None
    assert jumpbox.dst_user == "admin"


def test_all_from_upload_host(metadata):
    content = (FIXTURES / "ssh_config").read_bytes()
    result = SshConfigParser().parse(content, metadata)
    assert all(c.src_ip == "__upload_host__" for c in result.connections_found)


def test_empty_file(metadata):
    result = SshConfigParser().parse(b"", metadata)
    assert result.connections_found == []
