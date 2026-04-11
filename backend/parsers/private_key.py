"""Parser for SSH private key files (id_rsa, id_ed25519, etc.)."""
from __future__ import annotations

from parsers import BaseParser, CredentialData, ParseResult, UploadMetadata


def _load_private_key(content: bytes, passphrase: str | None = None):
    """Try to load a private key with paramiko. Returns (key_obj, key_type) or raises."""
    import paramiko

    loaders = [
        paramiko.RSAKey,
        paramiko.ECDSAKey,
    ]
    # Ed25519Key and DSSKey may not exist in all paramiko versions
    for name in ("Ed25519Key",):
        cls = getattr(paramiko, name, None)
        if cls is not None:
            loaders.append(cls)
    pw = passphrase.encode() if passphrase else None
    import io

    for loader in loaders:
        try:
            key = loader.from_private_key(io.StringIO(content.decode("utf-8", errors="replace")), password=pw)
            return key, key.get_name()
        except paramiko.ssh_exception.PasswordRequiredException:
            raise  # propagate — caller should report "key is encrypted"
        except Exception:
            continue
    return None, None


class PrivateKeyParser(BaseParser):
    """Parses SSH private key files — stores as Credential(found_on_disk) and cross-references fingerprints."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        filename = metadata.filename or "private_key"
        username = metadata.username

        text = content.decode("utf-8", errors="replace")

        if "PRIVATE KEY" not in text and "BEGIN DSA" not in text:
            result.warnings.append("File does not appear to contain a PEM-encoded private key")
            return result

        try:
            key, key_type = _load_private_key(content)
            if key is None:
                result.warnings.append("Could not parse private key — unsupported format or corrupted")
                return result
        except Exception as e:
            # _load_private_key only propagates PasswordRequiredException;
            # check the exact class name to avoid importing paramiko at module level.
            if type(e).__name__ == "PasswordRequiredException":
                # Still store it — we just can't compute fingerprint
                result.warnings.append(
                    "Private key is passphrase-protected — stored without fingerprint. "
                    "Supply the passphrase via the API if you want cross-referencing."
                )
                cred = CredentialData(
                    cred_type="private_key",
                    value=text,
                    username=username,
                    relationship_type="found_on_disk",
                    name=f"{filename}" + (f" ({username})" if username else ""),
                )
                result.credentials_found.append(cred)
            else:
                result.warnings.append(f"Failed to parse private key: {e}")
            return result

        cred = CredentialData(
            cred_type="private_key",
            value=text,
            username=username,
            relationship_type="found_on_disk",
            name=f"{filename}" + (f" ({username})" if username else ""),
        )
        result.credentials_found.append(cred)

        if username:
            result.host_users_found.append((username, None, None))

        # Compute SHA256 fingerprint from the raw public key blob
        try:
            import base64
            import hashlib
            raw = bytes(key.asbytes())
            digest = hashlib.sha256(raw).digest()
            b64 = base64.b64encode(digest).decode().rstrip("=")
            fp_str = f"SHA256:{b64}"
            result.stats["fingerprint"] = fp_str
        except Exception as e:
            result.warnings.append(f"Could not compute fingerprint: {e}")

        result.stats["key_type"] = key_type or "unknown"
        return result
