"""CRUD endpoints for Credentials and CredentialLinks."""
import base64
import hashlib
import io
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Credential, CredentialLink, Host, Operation
from schemas import (
    CredentialCreate,
    CredentialLinkCreate,
    CredentialLinkRead,
    CredentialLinkUpdate,
    CredentialRead,
    CredentialUpdate,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["credentials"])


def _infer_key_info(value: str, passphrase: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Parse a private key with paramiko and return (key_type, sha256_fingerprint).

    Returns (None, None) on any failure — never raises.
    """
    try:
        import paramiko

        pw = passphrase.encode() if passphrase else None
        f = io.StringIO(value)

        for cls in (
            paramiko.RSAKey,
            paramiko.Ed25519Key,
            paramiko.ECDSAKey,
            paramiko.DSSKey,
        ):
            try:
                key = cls.from_private_key(f, password=pw)
                pub_bytes = key.asbytes()
                digest = hashlib.sha256(pub_bytes).digest()
                fingerprint = "SHA256:" + base64.b64encode(digest).rstrip(b"=").decode()
                return key.get_name(), fingerprint
            except Exception:
                f.seek(0)

    except Exception:
        log.debug("paramiko key inference failed", exc_info=True)

    return None, None


def _get_op_or_404(op_id: str, db: Session) -> Operation:
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    return op


def _get_cred_or_404(cred_id: str, db: Session) -> Credential:
    cred = db.query(Credential).filter(Credential.id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    return cred


# ─── Credentials ──────────────────────────────────────────────────────────────

@router.post("/ops/{op_id}/credentials", response_model=CredentialRead, status_code=201)
def create_credential(op_id: str, body: CredentialCreate, db: Session = Depends(get_db)):
    _get_op_or_404(op_id, db)

    key_type, fingerprint = None, None
    if body.cred_type == "private_key":
        key_type, fingerprint = _infer_key_info(body.value, body.passphrase)

    cred = Credential(
        op_id=op_id,
        cred_type=body.cred_type,
        value=body.value,
        passphrase=body.passphrase,
        fingerprint=fingerprint,
        key_type=key_type,
        comment=body.comment,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


@router.get("/ops/{op_id}/credentials", response_model=List[CredentialRead])
def list_credentials(op_id: str, db: Session = Depends(get_db)):
    _get_op_or_404(op_id, db)
    return (
        db.query(Credential)
        .filter(Credential.op_id == op_id)
        .order_by(Credential.created_at.asc())
        .all()
    )


@router.get("/credentials/{cred_id}", response_model=CredentialRead)
def get_credential(cred_id: str, db: Session = Depends(get_db)):
    return _get_cred_or_404(cred_id, db)


@router.patch("/credentials/{cred_id}", response_model=CredentialRead)
def update_credential(cred_id: str, body: CredentialUpdate, db: Session = Depends(get_db)):
    cred = _get_cred_or_404(cred_id, db)
    if body.value is not None:
        cred.value = body.value
        # Re-infer key info when value changes (for private keys)
        if cred.cred_type == "private_key":
            passphrase = body.passphrase if body.passphrase is not None else cred.passphrase
            cred.key_type, cred.fingerprint = _infer_key_info(body.value, passphrase)
    if body.passphrase is not None:
        cred.passphrase = body.passphrase
        # Re-infer fingerprint if passphrase changed (encrypted key needs correct passphrase)
        if cred.cred_type == "private_key" and body.value is None:
            cred.key_type, cred.fingerprint = _infer_key_info(cred.value, body.passphrase)
    if body.comment is not None:
        cred.comment = body.comment
    db.commit()
    db.refresh(cred)
    return cred


@router.delete("/credentials/{cred_id}", status_code=204)
def delete_credential(cred_id: str, db: Session = Depends(get_db)):
    cred = _get_cred_or_404(cred_id, db)
    db.delete(cred)
    db.commit()


# ─── CredentialLinks ──────────────────────────────────────────────────────────

@router.post("/credential-links", response_model=CredentialLinkRead, status_code=201)
def create_credential_link(body: CredentialLinkCreate, db: Session = Depends(get_db)):
    _get_cred_or_404(body.credential_id, db)
    host = db.query(Host).filter(Host.id == body.host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    link = CredentialLink(
        credential_id=body.credential_id,
        host_id=body.host_id,
        username=body.username,
        host_user_id=body.host_user_id,
        relationship_type=body.relationship_type,
        file_source=body.file_source,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.get("/ops/{op_id}/credential-links", response_model=List[CredentialLinkRead])
def list_credential_links(op_id: str, db: Session = Depends(get_db)):
    _get_op_or_404(op_id, db)
    return (
        db.query(CredentialLink)
        .join(Credential, CredentialLink.credential_id == Credential.id)
        .filter(Credential.op_id == op_id)
        .all()
    )


@router.patch("/credential-links/{link_id}", response_model=CredentialLinkRead)
def update_credential_link(link_id: str, body: CredentialLinkUpdate, db: Session = Depends(get_db)):
    link = db.query(CredentialLink).filter(CredentialLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Credential link not found")
    if body.username is not None:
        link.username = body.username
    if body.host_user_id is not None:
        link.host_user_id = body.host_user_id
    if body.relationship_type is not None:
        link.relationship_type = body.relationship_type
    if body.file_source is not None:
        link.file_source = body.file_source
    db.commit()
    db.refresh(link)
    return link


@router.delete("/credential-links/{link_id}", status_code=204)
def delete_credential_link(link_id: str, db: Session = Depends(get_db)):
    link = db.query(CredentialLink).filter(CredentialLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Credential link not found")
    db.delete(link)
    db.commit()
