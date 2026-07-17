"""CRUD endpoints for Credentials and CredentialLinks."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Credential, CredentialLink, Host, HostUser
from routers.deps import get_cred_or_404, get_op_or_404
from schemas import (
    CredentialCreate,
    CredentialLinkCreate,
    CredentialLinkRead,
    CredentialLinkUpdate,
    CredentialRead,
    CredentialUpdate,
)
from services.activity import log_activity
from services.key_utils import infer_key_info
from ws_manager import broadcast_sync

log = logging.getLogger(__name__)

router = APIRouter(tags=["credentials"])


def _require_host_user_on_host(db: Session, host_user_id, host_id) -> None:
    """Reject a host_user_id that doesn't belong to the link's host."""
    if host_user_id is not None and not db.query(HostUser.id).filter(
        HostUser.id == host_user_id, HostUser.host_id == host_id
    ).first():
        raise HTTPException(status_code=400, detail="host_user_id does not belong to host_id")


# ─── Credentials ──────────────────────────────────────────────────────────────

@router.post("/ops/{op_id}/credentials", response_model=CredentialRead, status_code=201)
def create_credential(op_id: str, body: CredentialCreate, db: Session = Depends(get_db)):
    get_op_or_404(op_id, db)

    key_type, fingerprint = None, None
    if body.cred_type in ("private_key", "public_key"):
        key_type, fingerprint = infer_key_info(body.value, body.passphrase)

    cred = Credential(
        op_id=op_id,
        cred_type=body.cred_type,
        name=body.name,
        value=body.value,
        passphrase=body.passphrase,
        fingerprint=fingerprint,
        key_type=key_type,
        comment=body.comment,
    )
    db.add(cred)
    label = cred.name or (cred.fingerprint[:22] if cred.fingerprint else cred.cred_type)
    log_activity(db, op_id, "credential.create", "credential", detail=f"Added {cred.cred_type}: {label}")
    db.commit()
    db.refresh(cred)
    broadcast_sync(op_id, {"type": "update", "entity_type": "credential", "entity_id": cred.id, "op_id": op_id})
    return cred


@router.get("/ops/{op_id}/credentials", response_model=list[CredentialRead])
def list_credentials(op_id: str, db: Session = Depends(get_db)):
    get_op_or_404(op_id, db)
    return (
        db.query(Credential)
        .filter(Credential.op_id == op_id)
        .order_by(Credential.created_at.asc())
        .all()
    )


@router.get("/credentials/{cred_id}", response_model=CredentialRead)
def get_credential(cred_id: str, db: Session = Depends(get_db)):
    return get_cred_or_404(cred_id, db)


@router.patch("/credentials/{cred_id}", response_model=CredentialRead)
def update_credential(cred_id: str, body: CredentialUpdate, db: Session = Depends(get_db)):
    cred = get_cred_or_404(cred_id, db)
    if body.name is not None:
        cred.name = body.name or None
    if body.value is not None:
        cred.value = body.value
        # Re-infer key info when value changes (for private and public keys)
        if cred.cred_type in ("private_key", "public_key"):
            passphrase = body.passphrase if body.passphrase is not None else cred.passphrase
            cred.key_type, cred.fingerprint = infer_key_info(body.value, passphrase)
    if body.passphrase is not None:
        cred.passphrase = body.passphrase
        # Re-infer fingerprint if passphrase changed (encrypted key needs correct passphrase)
        if cred.cred_type == "private_key" and body.value is None:
            cred.key_type, cred.fingerprint = infer_key_info(cred.value, body.passphrase)
    if body.comment is not None:
        cred.comment = body.comment
    log_activity(db, cred.op_id, "credential.update", "credential", entity_id=cred_id)
    db.commit()
    db.refresh(cred)
    broadcast_sync(cred.op_id, {"type": "update", "entity_type": "credential", "entity_id": cred_id, "op_id": cred.op_id})
    return cred


@router.delete("/credentials/{cred_id}", status_code=204)
def delete_credential(cred_id: str, db: Session = Depends(get_db)):
    cred = get_cred_or_404(cred_id, db)
    label = cred.name or (cred.fingerprint[:22] if cred.fingerprint else cred.cred_type)
    op_id = cred.op_id
    log_activity(db, op_id, "credential.delete", "credential", entity_id=cred_id, detail=f"Deleted {cred.cred_type}: {label}")
    db.delete(cred)
    db.commit()
    broadcast_sync(op_id, {"type": "update", "entity_type": "credential", "entity_id": cred_id, "op_id": op_id})


# ─── CredentialLinks ──────────────────────────────────────────────────────────

@router.post("/credential-links", response_model=CredentialLinkRead, status_code=201)
def create_credential_link(body: CredentialLinkCreate, db: Session = Depends(get_db)):
    cred = get_cred_or_404(body.credential_id, db)
    host = db.query(Host).filter(Host.id == body.host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")
    if cred.op_id != host.op_id:
        raise HTTPException(status_code=400, detail="Credential and host belong to different operations")
    _require_host_user_on_host(db, body.host_user_id, body.host_id)

    link = CredentialLink(
        credential_id=body.credential_id,
        host_id=body.host_id,
        username=body.username,
        host_user_id=body.host_user_id,
        relationship_type=body.relationship_type,
        file_source=body.file_source,
    )
    db.add(link)
    log_activity(db, host.op_id, "credential_link.create", "credential",
                 entity_id=body.credential_id,
                 detail=f"Linked credential to '{host.nickname}'" + (f" @{body.username}" if body.username else ""))
    db.commit()
    db.refresh(link)
    broadcast_sync(cred.op_id, {"type": "update", "entity_type": "credential", "entity_id": body.credential_id, "op_id": cred.op_id})
    return link


@router.get("/ops/{op_id}/credential-links", response_model=list[CredentialLinkRead])
def list_credential_links(op_id: str, db: Session = Depends(get_db)):
    get_op_or_404(op_id, db)
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
    _require_host_user_on_host(db, body.host_user_id, link.host_id)
    if body.username is not None:
        link.username = body.username
    if body.host_user_id is not None:
        link.host_user_id = body.host_user_id
    if body.relationship_type is not None:
        link.relationship_type = body.relationship_type
    if body.file_source is not None:
        link.file_source = body.file_source
    cred_for_log = db.get(Credential, link.credential_id)
    if cred_for_log:
        log_activity(db, cred_for_log.op_id, "credential_link.update", "credential", entity_id=link.credential_id)
    else:
        host_for_log = db.get(Host, link.host_id)
        if host_for_log:
            log_activity(db, host_for_log.op_id, "credential_link.update", "credential", entity_id=link_id)
        else:
            raise HTTPException(status_code=409, detail="CredentialLink references no existing credential or host")
    db.commit()
    db.refresh(link)
    cred = db.get(Credential, link.credential_id)
    if cred:
        broadcast_sync(cred.op_id, {"type": "update", "entity_type": "credential", "entity_id": link.credential_id, "op_id": cred.op_id})
    return link


@router.delete("/credential-links/{link_id}", status_code=204)
def delete_credential_link(link_id: str, db: Session = Depends(get_db)):
    link = db.query(CredentialLink).filter(CredentialLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Credential link not found")
    cred = db.get(Credential, link.credential_id)
    op_id = cred.op_id if cred else None
    cred_id = link.credential_id
    if not cred:
        log.warning("Orphaned CredentialLink %s references missing Credential %s", link_id, link.credential_id)
    if op_id:
        log_activity(db, op_id, "credential_link.delete", "credential",
                     entity_id=cred_id, detail="Removed credential link")
    db.delete(link)
    db.commit()
    if op_id:
        broadcast_sync(op_id, {"type": "update", "entity_type": "credential", "entity_id": cred_id, "op_id": op_id})
