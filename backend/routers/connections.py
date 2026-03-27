"""CRUD endpoints for ConnectionRecords."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ConnectionRecord, Operation
from schemas import ConnectionRecordCreate, ConnectionRecordRead

router = APIRouter(tags=["connections"])


def _get_op_or_404(op_id: str, db: Session) -> Operation:
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    return op


@router.post("/ops/{op_id}/connections", response_model=ConnectionRecordRead, status_code=201)
def create_connection(
    op_id: str,
    body: ConnectionRecordCreate,
    db: Session = Depends(get_db),
):
    _get_op_or_404(op_id, db)
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
        timestamp=body.timestamp,
        raw_line=body.raw_line,
        source_file=body.source_file,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/ops/{op_id}/connections", response_model=List[ConnectionRecordRead])
def list_connections(
    op_id: str,
    src_host_id: Optional[str] = None,
    dst_host_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _get_op_or_404(op_id, db)
    q = db.query(ConnectionRecord).filter(ConnectionRecord.op_id == op_id)
    if src_host_id:
        q = q.filter(ConnectionRecord.src_host_id == src_host_id)
    if dst_host_id:
        q = q.filter(ConnectionRecord.dst_host_id == dst_host_id)
    return q.order_by(ConnectionRecord.created_at.asc()).all()


@router.get("/connections/{connection_id}", response_model=ConnectionRecordRead)
def get_connection(connection_id: str, db: Session = Depends(get_db)):
    record = db.query(ConnectionRecord).filter(ConnectionRecord.id == connection_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Connection record not found")
    return record


@router.delete("/connections/{connection_id}", status_code=204)
def delete_connection(connection_id: str, db: Session = Depends(get_db)):
    record = db.query(ConnectionRecord).filter(ConnectionRecord.id == connection_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Connection record not found")
    db.delete(record)
    db.commit()
