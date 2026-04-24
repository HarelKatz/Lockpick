"""CRUD endpoints for Hosts and HostIPs."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Host, HostIP, HostNote, HostUser, SudoRule
from routers.deps import get_host_or_404, get_op_or_404
from services.activity import log_activity
from services.ssh_pattern import apply_patterns_to_host
from ws_manager import broadcast_sync
from schemas import (
    HostCreate,
    HostIPCreate,
    HostIPRead,
    HostNoteCreate,
    HostNoteRead,
    HostRead,
    HostUpdate,
    HostUserCreate,
    HostUserRead,
    SudoRuleRead,
)

router = APIRouter(tags=["hosts"])


# ─── Hosts ────────────────────────────────────────────────────────────────────

@router.post("/ops/{op_id}/hosts", response_model=HostRead, status_code=201)
def create_host(op_id: str, body: HostCreate, db: Session = Depends(get_db)):
    get_op_or_404(op_id, db)
    host = Host(op_id=op_id, nickname=body.nickname, comment=body.comment)
    db.add(host)
    db.flush()
    log_activity(db, op_id, "host.create", "host", detail=f"Added host '{body.nickname}'")
    apply_patterns_to_host(db, host)
    db.commit()
    db.refresh(host)
    broadcast_sync(op_id, {"type": "update", "entity_type": "host", "entity_id": host.id, "op_id": op_id})
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
    if "status" in body.model_fields_set:
        host.status = body.status  # None clears it; a valid string sets it
    log_activity(db, host.op_id, "host.update", "host", entity_id=host_id, detail=f"Updated host '{host.nickname}'")
    db.commit()
    db.refresh(host)
    broadcast_sync(host.op_id, {"type": "update", "entity_type": "host", "entity_id": host_id, "op_id": host.op_id})
    return host


@router.delete("/hosts/{host_id}", status_code=204)
def delete_host(host_id: str, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    op_id = host.op_id
    log_activity(db, op_id, "host.delete", "host", entity_id=host_id, detail=f"Deleted host '{host.nickname}'")
    db.delete(host)
    db.commit()
    broadcast_sync(op_id, {"type": "update", "entity_type": "host", "entity_id": host_id, "op_id": op_id})


# ─── HostIPs ──────────────────────────────────────────────────────────────────

@router.post("/hosts/{host_id}/ips", response_model=HostIPRead, status_code=201)
def add_host_ip(host_id: str, body: HostIPCreate, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    ip = HostIP(
        host_id=host_id,
        ip_address=body.ip_address,
        source=body.source,
        addr_type=body.addr_type,
    )
    db.add(ip)
    db.flush()
    db.refresh(host)  # pick up the new IP for pattern matching
    log_activity(db, host.op_id, "host_ip.add", "host", entity_id=host_id, detail=f"Added IP {body.ip_address} to '{host.nickname}'")
    apply_patterns_to_host(db, host)
    db.commit()
    db.refresh(ip)
    broadcast_sync(host.op_id, {"type": "update", "entity_type": "host", "entity_id": host_id, "op_id": host.op_id})
    return ip


@router.get("/hosts/{host_id}/ips", response_model=list[HostIPRead])
def list_host_ips(host_id: str, db: Session = Depends(get_db)):
    get_host_or_404(host_id, db)
    return db.query(HostIP).filter(HostIP.host_id == host_id).all()


@router.delete("/hosts/{host_id}/ips/{ip_id}", status_code=204)
def delete_host_ip(host_id: str, ip_id: str, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    ip = db.query(HostIP).filter(HostIP.id == ip_id, HostIP.host_id == host_id).first()
    if not ip:
        raise HTTPException(status_code=404, detail="IP not found")
    log_activity(db, host.op_id, "host_ip.delete", "host", entity_id=host_id, detail=f"Removed IP {ip.ip_address} from '{host.nickname}'")
    db.delete(ip)
    db.commit()
    broadcast_sync(host.op_id, {"type": "update", "entity_type": "host", "entity_id": host_id, "op_id": host.op_id})


# ─── HostUsers ────────────────────────────────────────────────────────────────

@router.post("/hosts/{host_id}/users", response_model=HostUserRead, status_code=201)
def create_host_user(host_id: str, body: HostUserCreate, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    user = HostUser(
        host_id=host_id,
        username=body.username,
        shell=body.shell,
        home_dir=body.home_dir,
        source=body.source,
    )
    db.add(user)
    db.flush()
    log_activity(db, host.op_id, "host_user.create", "host", entity_id=host_id, detail=f"Added user '{body.username}' to '{host.nickname}'")
    db.commit()
    db.refresh(user)
    broadcast_sync(host.op_id, {"type": "update", "entity_type": "host", "entity_id": host_id, "op_id": host.op_id})
    return user


@router.get("/hosts/{host_id}/users", response_model=list[HostUserRead])
def list_host_users(host_id: str, db: Session = Depends(get_db)):
    get_host_or_404(host_id, db)
    return db.query(HostUser).filter(HostUser.host_id == host_id).all()


@router.delete("/hosts/{host_id}/users/{user_id}", status_code=204)
def delete_host_user(host_id: str, user_id: str, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    user = db.query(HostUser).filter(HostUser.id == user_id, HostUser.host_id == host_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    log_activity(db, host.op_id, "host_user.delete", "host", entity_id=host_id, detail=f"Deleted user '{user.username}' from '{host.nickname}'")
    db.delete(user)
    db.commit()
    broadcast_sync(host.op_id, {"type": "update", "entity_type": "host", "entity_id": host_id, "op_id": host.op_id})


# ─── SudoRules ────────────────────────────────────────────────────────────────

@router.get("/hosts/{host_id}/sudo-rules", response_model=list[SudoRuleRead])
def list_sudo_rules(host_id: str, db: Session = Depends(get_db)):
    get_host_or_404(host_id, db)
    return (
        db.query(SudoRule)
        .filter(SudoRule.host_id == host_id)
        .order_by(SudoRule.created_at.asc())
        .all()
    )


@router.delete("/hosts/{host_id}/sudo-rules/{rule_id}", status_code=204)
def delete_sudo_rule(host_id: str, rule_id: str, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    rule = db.query(SudoRule).filter(SudoRule.id == rule_id, SudoRule.host_id == host_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Sudo rule not found")
    log_activity(db, host.op_id, "sudo_rule.delete", "sudo_rule", entity_id=rule_id,
                 detail=f"Deleted sudo rule for subject '{rule.subject}' on host '{host.nickname}'")
    db.delete(rule)
    db.commit()
    broadcast_sync(host.op_id, {"type": "update", "entity_type": "host", "entity_id": host_id, "op_id": host.op_id})


# ─── HostNotes ────────────────────────────────────────────────────────────────

@router.post("/hosts/{host_id}/notes", response_model=HostNoteRead, status_code=201)
def create_host_note(host_id: str, body: HostNoteCreate, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    note = HostNote(op_id=host.op_id, host_id=host_id, content=body.content)
    db.add(note)
    db.flush()
    log_activity(db, host.op_id, "host_note.create", "host_note", entity_id=note.id,
                 detail=f"Added note to host '{host.nickname}'")
    db.commit()
    db.refresh(note)
    broadcast_sync(host.op_id, {"type": "update", "entity_type": "host", "entity_id": host_id, "op_id": host.op_id})
    return note


@router.get("/hosts/{host_id}/notes", response_model=list[HostNoteRead])
def list_host_notes(host_id: str, db: Session = Depends(get_db)):
    get_host_or_404(host_id, db)
    return (
        db.query(HostNote)
        .filter(HostNote.host_id == host_id)
        .order_by(HostNote.created_at.asc())
        .all()
    )


@router.delete("/hosts/{host_id}/notes/{note_id}", status_code=204)
def delete_host_note(host_id: str, note_id: str, db: Session = Depends(get_db)):
    host = get_host_or_404(host_id, db)
    note = db.query(HostNote).filter(HostNote.id == note_id, HostNote.host_id == host_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    log_activity(db, host.op_id, "host_note.delete", "host_note", entity_id=note_id,
                 detail=f"Deleted note from host '{host.nickname}'")
    db.delete(note)
    db.commit()
    broadcast_sync(host.op_id, {"type": "update", "entity_type": "host", "entity_id": host_id, "op_id": host.op_id})
