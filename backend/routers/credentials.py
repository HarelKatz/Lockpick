"""CRUD endpoints for Credentials and CredentialLinks."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Credential, CredentialLink, Operation
from schemas import (
    CredentialCreate,
    CredentialLinkCreate,
    CredentialLinkRead,
    CredentialRead,
    CredentialUpdate,
)

router = APIRouter(tags=["credentials"])


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
    cred = Credential(
        op_id=op_id,
        cred_type=body.cred_type,
        value=body.value,
        fingerprint=body.fingerprint,
        key_type=body.key_type,
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
    if body.comment is not None:
        cred.comment = body.comment
    if body.fingerprint is not None:
        cred.fingerprint = body.fingerprint
    if body.key_type is not None:
        cred.key_type = body.key_type
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
    # Validate referenced entities exist
    _get_cred_or_404(body.credential_id, db)
    from models import Host
    host = db.query(Host).filter(Host.id == body.host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    link = CredentialLink(
        credential_id=body.credential_id,
        host_id=body.host_id,
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


@router.delete("/credential-links/{link_id}", status_code=204)
def delete_credential_link(link_id: str, db: Session = Depends(get_db)):
    link = db.query(CredentialLink).filter(CredentialLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Credential link not found")
    db.delete(link)
    db.commit()
