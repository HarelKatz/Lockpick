"""CRUD endpoints for Operations."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from routers.deps import get_op_or_404
from schemas import OperationCreate, OperationRead, OperationUpdate
from models import Operation
from services.activity import log_activity
from ws_manager import broadcast_sync

router = APIRouter(tags=["operations"])


@router.post("/ops", response_model=OperationRead, status_code=201)
def create_operation(body: OperationCreate, db: Session = Depends(get_db)):
    op = Operation(name=body.name, description=body.description)
    db.add(op)
    db.flush()
    log_activity(db, op.id, "operation.create", "operation", detail=f"Created operation '{op.name}'")
    db.commit()
    db.refresh(op)
    broadcast_sync(op.id, {"type": "update", "entity_type": "operation", "op_id": op.id})
    return op


@router.get("/ops", response_model=list[OperationRead])
def list_operations(db: Session = Depends(get_db)):
    return db.query(Operation).order_by(Operation.created_at.desc()).all()


@router.get("/ops/{op_id}", response_model=OperationRead)
def get_operation(op_id: str, db: Session = Depends(get_db)):
    return get_op_or_404(op_id, db)


@router.patch("/ops/{op_id}", response_model=OperationRead)
def update_operation(op_id: str, body: OperationUpdate, db: Session = Depends(get_db)):
    op = get_op_or_404(op_id, db)
    if body.name is not None:
        op.name = body.name
    if body.description is not None:
        op.description = body.description
    log_activity(db, op.id, "operation.update", "operation", entity_id=op.id, detail=f"Updated operation '{op.name}'")
    db.commit()
    db.refresh(op)
    broadcast_sync(op.id, {"type": "update", "entity_type": "operation", "op_id": op.id})
    return op


@router.delete("/ops/{op_id}", status_code=204)
def delete_operation(op_id: str, db: Session = Depends(get_db)):
    op = get_op_or_404(op_id, db)
    op_id = op.id
    log_activity(db, op_id, "operation.delete", "operation", entity_id=op_id, detail=f"Deleted operation '{op.name}'")
    db.delete(op)
    db.commit()
    broadcast_sync(op_id, {"type": "update", "entity_type": "operation", "op_id": op_id})
