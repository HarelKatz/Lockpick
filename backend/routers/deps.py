"""Shared router dependencies — entity lookups that raise 404 on miss."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import ConnectionRecord, Credential, Host, Operation


def get_op_or_404(op_id: str, db: Session) -> Operation:
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    return op


def get_host_or_404(host_id: str, db: Session) -> Host:
    host = db.query(Host).filter(Host.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")
    return host


def get_cred_or_404(cred_id: str, db: Session) -> Credential:
    cred = db.query(Credential).filter(Credential.id == cred_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    return cred


def get_connection_or_404(connection_id: str, db: Session) -> ConnectionRecord:
    record = db.query(ConnectionRecord).filter(ConnectionRecord.id == connection_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Connection record not found")
    return record
