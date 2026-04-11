"""CRUD endpoints for Operations."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Operation
from schemas import OperationCreate, OperationRead, OperationUpdate

router = APIRouter(tags=["operations"])


def _get_op_or_404(db: Session, op_id: str) -> Operation:
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    return op


@router.post("/ops", response_model=OperationRead, status_code=201)
def create_operation(body: OperationCreate, db: Session = Depends(get_db)):
    op = Operation(name=body.name, description=body.description)
    db.add(op)
    db.commit()
    db.refresh(op)
    return op


@router.get("/ops", response_model=list[OperationRead])
def list_operations(db: Session = Depends(get_db)):
    return db.query(Operation).order_by(Operation.created_at.desc()).all()


@router.get("/ops/{op_id}", response_model=OperationRead)
def get_operation(op_id: str, db: Session = Depends(get_db)):
    return _get_op_or_404(db, op_id)


@router.patch("/ops/{op_id}", response_model=OperationRead)
def update_operation(op_id: str, body: OperationUpdate, db: Session = Depends(get_db)):
    op = _get_op_or_404(db, op_id)
    if body.name is not None:
        op.name = body.name
    if body.description is not None:
        op.description = body.description
    db.commit()
    db.refresh(op)
    return op


@router.delete("/ops/{op_id}", status_code=204)
def delete_operation(op_id: str, db: Session = Depends(get_db)):
    op = _get_op_or_404(db, op_id)
    db.delete(op)
    db.commit()
