"""GET /ops/{op_id}/activity — recent activity log entries."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import ActivityLog, Operation
from schemas import ActivityLogRead

router = APIRouter()


@router.get("/ops/{op_id}/activity", response_model=list[ActivityLogRead])
def get_activity(
    op_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    if not db.get(Operation, op_id):
        raise HTTPException(status_code=404, detail="Operation not found")
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.op_id == op_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
        .all()
    )
