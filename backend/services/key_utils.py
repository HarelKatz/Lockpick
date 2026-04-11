"""SSH key fingerprint and type inference utilities.

Single source of truth for computing (key_type, sha256_fingerprint) from
raw key material.  Used by:
  - routers/upload.py      — when ingesting parsed credentials
  - routers/credentials.py — when a credential is created or updated manually
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
from typing import Optional

log = logging.getLogger(__name__)


def infer_key_info(
    value: str,
    passphrase: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Return (key_type, sha256_fingerprint) for an SSH key value.

    Tries private key formats first (RSA, Ed25519, ECDSA, DSS), then falls
    back to public-key format (``keytype base64 [comment]``).

    Returns ``(None, None)`` on any failure — never raises.
    """
    try:
        import paramiko

        pw = passphrase.encode() if passphrase else None
        f = io.StringIO(value)

        # Build the list dynamically — some paramiko versions omit DSSKey
        key_classes = [
            cls for name in ("RSAKey", "Ed25519Key", "ECDSAKey", "DSSKey")
            if (cls := getattr(paramiko, name, None)) is not None
        ]
        for cls in key_classes:
            try:
                key = cls.from_private_key(f, password=pw)
                raw = key.asbytes()
                fp = (
                    "SHA256:"
                    + base64.b64encode(hashlib.sha256(raw).digest())
                    .rstrip(b"=")
                    .decode()
                )
                return key.get_name(), fp
            except Exception:
                f.seek(0)

        # Fall back to public-key format: "keytype base64 [comment]"
        parts = value.strip().split()
        if len(parts) >= 2:
            raw = base64.b64decode(parts[1])
            fp = (
                "SHA256:"
                + base64.b64encode(hashlib.sha256(raw).digest())
                .rstrip(b"=")
                .decode()
            )
            return parts[0], fp

    except Exception:
        log.debug("key inference failed", exc_info=True)

    return None, None
