"""CRUD endpoints for ConnectionRecords."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ConnectionRecord, Credential
from routers.deps import get_connection_or_404, get_op_or_404
from services.activity import log_activity
from schemas import ConnectionRecordCreate, ConnectionRecordRead, ConnectionRecordUpdate
from ws_manager import broadcast_sync

router = APIRouter(tags=["connections"])


@router.post("/ops/{op_id}/connections", response_model=ConnectionRecordRead, status_code=201)
def create_connection(
    op_id: str,
    body: ConnectionRecordCreate,
    db: Session = Depends(get_db),
):
    get_op_or_404(op_id, db)
    if body.credential_id is not None:
        cred = db.query(Credential).filter(
            Credential.id == body.credential_id,
            Credential.op_id == op_id,
        ).first()
        if not cred:
            raise HTTPException(status_code=400, detail="credential_id not found in this operation")
    record = ConnectionRecord(
        op_id=op_id,
        src_host_id=body.src_host_id,
        src_ip=body.src_ip,
        src_user=body.src_user,
        dst_host_id=body.dst_host_id,
        dst_ip=body.dst_ip,
        dst_user=body.dst_user,
        connection_type=body.connection_type,
        direction_context=body.direction_context,
        auth_method=body.auth_method,
        credential_id=body.credential_id,
        timestamp=body.timestamp,
        raw_line=body.raw_line,
        source_file=body.source_file,
    )
    db.add(record)
    src = body.src_ip or "?"
    dst = body.dst_ip or "?"
    log_activity(db, op_id, "connection.create", "connection",
                 detail=f"Added {body.connection_type} connection: {src} → {dst}")
    db.commit()
    db.refresh(record)
    broadcast_sync(op_id, {"type": "update", "entity_type": "connection", "entity_id": record.id, "op_id": op_id})
    return record


@router.get("/ops/{op_id}/connections", response_model=list[ConnectionRecordRead])
def list_connections(
    op_id: str,
    src_host_id: Optional[str] = None,
    dst_host_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    get_op_or_404(op_id, db)
    q = db.query(ConnectionRecord).filter(ConnectionRecord.op_id == op_id)
    if src_host_id:
        q = q.filter(ConnectionRecord.src_host_id == src_host_id)
    if dst_host_id:
        q = q.filter(ConnectionRecord.dst_host_id == dst_host_id)
    return q.order_by(ConnectionRecord.created_at.asc()).all()


@router.get("/connections/{connection_id}", response_model=ConnectionRecordRead)
def get_connection(connection_id: str, db: Session = Depends(get_db)):
    return get_connection_or_404(connection_id, db)


@router.patch("/connections/{connection_id}", response_model=ConnectionRecordRead)
def update_connection(connection_id: str, body: ConnectionRecordUpdate, db: Session = Depends(get_db)):
    record = get_connection_or_404(connection_id, db)
    for field in (
        "src_host_id", "src_ip", "src_user",
        "dst_host_id", "dst_ip", "dst_user",
        "connection_type", "direction_context",
        "timestamp", "raw_line", "source_file",
    ):
        val = getattr(body, field)
        if val is not None:
            setattr(record, field, val)
    # auth_method and credential_id can be explicitly cleared to null
    for field in ("auth_method", "credential_id"):
        if field in body.model_fields_set:
            setattr(record, field, getattr(body, field))
    log_activity(db, record.op_id, "connection.update", "connection", entity_id=connection_id,
                 detail=f"Updated {record.connection_type} connection: {record.src_ip} → {record.dst_ip}")
    db.commit()
    db.refresh(record)
    broadcast_sync(record.op_id, {"type": "update", "entity_type": "connection", "entity_id": connection_id, "op_id": record.op_id})
    return record


@router.delete("/connections/{connection_id}", status_code=204)
def delete_connection(connection_id: str, db: Session = Depends(get_db)):
    record = get_connection_or_404(connection_id, db)
    op_id = record.op_id
    log_activity(db, op_id, "connection.delete", "connection",
                 entity_id=connection_id,
                 detail=f"Deleted {record.connection_type} connection: {record.src_ip} → {record.dst_ip}")
    db.delete(record)
    db.commit()
    broadcast_sync(op_id, {"type": "update", "entity_type": "connection", "entity_id": connection_id, "op_id": op_id})
