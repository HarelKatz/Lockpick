"""CRUD endpoints for Hosts and HostIPs."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Host, HostIP, HostUser
from routers.deps import get_host_or_404, get_op_or_404
from services.activity import log_activity
from schemas import (
    HostCreate,
    HostIPCreate,
    HostIPRead,
    HostRead,
    HostUpdate,
    HostUserCreate,
    HostUserRead,
)

router = APIRouter(tags=["hosts"])


# ─── Hosts ────────────────────────────────────────────────────────────────────

@router.post("/ops/{op_id}/hosts", response_model=HostRead, status_code=201)
def create_host(op_id: str, body: HostCreate, db: Session = Depends(get_db)):
    get_op_or_404(op_id, db)
    host = Host(op_id=op_id, nickname=body.nickname, comment=body.comment)
    db.add(host)
    log_activity(db, op_id, "host.create", "host", detail=f"Added host '{body.nickname}'")
    db.commit()
    db.refresh(host)
    return host


@router.get("/ops/{op_id}/hosts", response_model=list[HostRead])
def list_hosts(op_id: str, db: Session = Depends(get_db)):
    get_op_or_404(op_id, db)
    return (
        db.query(Host)
        .filter(Host.op_id == op_id)
        .order_by(Host.created_at.asc())
        .all()
    )


@router.get("/hosts/{host_id}", response_model=HostRead)
def get_host(host_id: str, db: Session = Depends(get_db)):
    return get_host_or_404(host_id, db)


@router.patch("/hosts/{host_id}", response_model=HostRead)
def update_host(host_id: str, body: HostUpdate, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    if body.nickname is not None:
        host.nickname = body.nickname
    if body.comment is not None:
        host.comment = body.comment
    log_activity(db, host.op_id, "host.update", "host", entity_id=host_id, detail=f"Updated host '{host.nickname}'")
    db.commit()
    db.refresh(host)
    return host


@router.delete("/hosts/{host_id}", status_code=204)
def delete_host(host_id: str, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    log_activity(db, host.op_id, "host.delete", "host", entity_id=host_id, detail=f"Deleted host '{host.nickname}'")
    db.delete(host)
    db.commit()


# ─── HostIPs ──────────────────────────────────────────────────────────────────

@router.post("/hosts/{host_id}/ips", response_model=HostIPRead, status_code=201)
def add_host_ip(host_id: str, body: HostIPCreate, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    ip = HostIP(
        host_id=host_id,
        ip_address=body.ip_address,
        source=body.source,
    )
    db.add(ip)
    log_activity(db, host.op_id, "host_ip.add", "host", entity_id=host_id, detail=f"Added IP {body.ip_address} to '{host.nickname}'")
    db.commit()
    db.refresh(ip)
    return ip


@router.get("/hosts/{host_id}/ips", response_model=list[HostIPRead])
def list_host_ips(host_id: str, db: Session = Depends(get_db)):
    get_host_or_404(host_id, db)
    return db.query(HostIP).filter(HostIP.host_id == host_id).all()


@router.delete("/hosts/{host_id}/ips/{ip_id}", status_code=204)
def delete_host_ip(host_id: str, ip_id: str, db: Session = Depends(get_db)):
    get_host_or_404(host_id, db)
    ip = db.query(HostIP).filter(HostIP.id == ip_id, HostIP.host_id == host_id).first()
    if not ip:
        raise HTTPException(status_code=404, detail="IP not found")
    db.delete(ip)
    db.commit()


# ─── HostUsers ────────────────────────────────────────────────────────────────

@router.post("/hosts/{host_id}/users", response_model=HostUserRead, status_code=201)
def create_host_user(host_id: str, body: HostUserCreate, db: Session = Depends(get_db)):
    get_host_or_404(host_id, db)
    user = HostUser(
        host_id=host_id,
        username=body.username,
        shell=body.shell,
        home_dir=body.home_dir,
        source=body.source,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/hosts/{host_id}/users", response_model=list[HostUserRead])
def list_host_users(host_id: str, db: Session = Depends(get_db)):
    get_host_or_404(host_id, db)
    return db.query(HostUser).filter(HostUser.host_id == host_id).all()


@router.delete("/hosts/{host_id}/users/{user_id}", status_code=204)
def delete_host_user(host_id: str, user_id: str, db: Session = Depends(get_db)):
    get_host_or_404(host_id, db)
    user = db.query(HostUser).filter(HostUser.id == user_id, HostUser.host_id == host_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
