"""GET /ops/{op_id}/stats — lightweight record count + latest activity timestamp."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import Operation, Host, Credential, ConnectionRecord
from schemas import OpStats

router = APIRouter()


@router.get("/ops/{op_id}/stats", response_model=OpStats)
def get_op_stats(op_id: str, db: Session = Depends(get_db)):
    if not db.get(Operation, op_id):
        raise HTTPException(status_code=404, detail="Operation not found")

    host_count = db.query(func.count(Host.id)).filter(Host.op_id == op_id).scalar() or 0
    cred_count = db.query(func.count(Credential.id)).filter(Credential.op_id == op_id).scalar() or 0
    conn_count = db.query(func.count(ConnectionRecord.id)).filter(ConnectionRecord.op_id == op_id).scalar() or 0

    latest_host = db.query(func.max(Host.created_at)).filter(Host.op_id == op_id).scalar()
    latest_cred = db.query(func.max(Credential.created_at)).filter(Credential.op_id == op_id).scalar()
    latest_conn = db.query(func.max(ConnectionRecord.created_at)).filter(ConnectionRecord.op_id == op_id).scalar()

    candidates = [t for t in [latest_host, latest_cred, latest_conn] if t is not None]
    latest_activity_at: datetime | None = max(candidates) if candidates else None

    return OpStats(
        host_count=host_count,
        credential_count=cred_count,
        connection_count=conn_count,
        total_records=host_count + cred_count + conn_count,
        latest_activity_at=latest_activity_at,
    )
