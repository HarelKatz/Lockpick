"""Unit tests for services/key_utils.py — infer_key_info()."""
from pathlib import Path

import pytest

from services.key_utils import infer_key_info

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def ed25519_keys():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()
    ).decode()
    pub_bytes = priv.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
    pub_str = pub_bytes.decode()
    return priv_pem, pub_str


@pytest.fixture(scope="module")
def rsa_encrypted_key():
    from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
    from cryptography.hazmat.primitives.serialization import (
        BestAvailableEncryption,
        Encoding,
        PrivateFormat,
    )

    passphrase = "testpass"
    key = generate_private_key(65537, 2048)
    pem = key.private_bytes(
        Encoding.PEM,
        PrivateFormat.TraditionalOpenSSL,
        BestAvailableEncryption(passphrase.encode()),
    ).decode()
    return pem, passphrase


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_rsa_private_key():
    content = (FIXTURES / "id_rsa").read_text()
    key_type, fp = infer_key_info(content)
    assert key_type == "ssh-rsa"
    assert fp is not None
    assert fp.startswith("SHA256:")


def test_rsa_public_key():
    content = (FIXTURES / "id_rsa.pub").read_text()
    key_type, fp = infer_key_info(content)
    assert key_type == "ssh-rsa"
    assert fp is not None
    assert fp.startswith("SHA256:")


def test_private_and_public_fingerprints_match():
    priv_content = (FIXTURES / "id_rsa").read_text()
    pub_content = (FIXTURES / "id_rsa.pub").read_text()
    _, fp_priv = infer_key_info(priv_content)
    _, fp_pub = infer_key_info(pub_content)
    assert fp_priv is not None
    assert fp_pub is not None
    assert fp_priv == fp_pub


def test_ed25519_private_key(ed25519_keys):
    priv_pem, _ = ed25519_keys
    key_type, fp = infer_key_info(priv_pem)
    assert key_type == "ssh-ed25519"
    assert fp is not None
    assert fp.startswith("SHA256:")


def test_ed25519_public_key(ed25519_keys):
    priv_pem, pub_str = ed25519_keys
    _, fp_priv = infer_key_info(priv_pem)
    _, fp_pub = infer_key_info(pub_str)
    assert fp_priv is not None
    assert fp_pub is not None
    assert fp_priv == fp_pub


def test_malformed_key_returns_none_none():
    key_type, fp = infer_key_info("not a key")
    assert key_type is None
    assert fp is None


def test_empty_string_returns_none_none():
    key_type, fp = infer_key_info("")
    assert key_type is None
    assert fp is None


def test_fingerprint_starts_with_sha256():
    content = (FIXTURES / "id_rsa").read_text()
    _, fp = infer_key_info(content)
    assert fp is not None
    assert fp.startswith("SHA256:")


def test_passphrase_encrypted_correct(rsa_encrypted_key):
    pem, passphrase = rsa_encrypted_key
    key_type, fp = infer_key_info(pem, passphrase=passphrase)
    assert key_type is not None
    assert fp is not None
    assert fp.startswith("SHA256:")


def test_passphrase_encrypted_no_passphrase(rsa_encrypted_key):
    pem, _ = rsa_encrypted_key
    key_type, fp = infer_key_info(pem)
    assert key_type is None
    assert fp is None
