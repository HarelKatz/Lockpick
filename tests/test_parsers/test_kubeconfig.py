"""Tests for KubeconfigParser."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.kubeconfig import KubeconfigParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "kubeconfig"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="kubeconfig",
        filename="config",
    )


def test_with_secrets(metadata):
    content = (FIXTURES / "with_secrets").read_bytes()
    result = KubeconfigParser().parse(content, metadata)

    # alice: token + client_key = 2
    # bob: password = 1
    # carol: refresh-token + id-token = 2
    # redacted: 0 (placeholders skipped)
    assert len(result.credentials_found) == 5
    assert result.stats == {"credentials": 5}

    by_name = {c.name: c for c in result.credentials_found}

    # alice token
    assert "kubeconfig:alice:token" in by_name
    assert by_name["kubeconfig:alice:token"].value == "bearer-token-xyz"
    assert by_name["kubeconfig:alice:token"].cred_type == "password"
    assert by_name["kubeconfig:alice:token"].username == "alice"

    # alice decoded client-key
    assert "kubeconfig:alice:client_key" in by_name
    alice_key = by_name["kubeconfig:alice:client_key"]
    assert alice_key.cred_type == "private_key"
    assert "BEGIN PRIVATE KEY" in alice_key.value
    assert alice_key.username == "alice"

    # bob basic auth
    assert "kubeconfig:bob:password" in by_name
    bob_pw = by_name["kubeconfig:bob:password"]
    assert bob_pw.value == "basicpw"
    assert bob_pw.username == "basic-bob"  # uses inner `username` field

    # carol auth-provider
    assert "kubeconfig:carol:refresh_token" in by_name
    assert by_name["kubeconfig:carol:refresh_token"].value == "oidc-refresh-token"
    assert "kubeconfig:carol:id_token" in by_name
    assert by_name["kubeconfig:carol:id_token"].value == "oidc-id-token"

    # redacted: nothing emitted
    assert "kubeconfig:redacted:token" not in by_name
    assert "kubeconfig:redacted:client_key" not in by_name


def test_invalid_yaml(metadata):
    content = b"::not yaml::\n  - bad: [unclosed"
    result = KubeconfigParser().parse(content, metadata)
    # should not crash; may emit YAML warning
    assert isinstance(result.credentials_found, list)


def test_empty_file(metadata):
    result = KubeconfigParser().parse(b"", metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_no_users(metadata):
    content = b"apiVersion: v1\nkind: Config\nclusters: []\n"
    result = KubeconfigParser().parse(content, metadata)
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_garbage_b64(metadata):
    content = b"""apiVersion: v1
kind: Config
users:
- name: garbage
  user:
    client-key-data: not_valid_base64_at_all_!!!
"""
    result = KubeconfigParser().parse(content, metadata)
    # should not crash, no key emitted
    assert all(c.name != "kubeconfig:garbage:client_key" for c in result.credentials_found)
