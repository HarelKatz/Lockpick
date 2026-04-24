"""Export and Import endpoints for Lockpick operations.

GET  /api/ops/{op_id}/export  — download full op as JSON
POST /api/ops/import          — create a new op from exported JSON
"""
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models import (
    ActivityLog,
    ConnectionRecord,
    Credential,
    CredentialLink,
    Host,
    HostIP,
    HostUser,
    Operation,
)
from schemas import (
    ExportActivityEntry,
    ExportConnection,
    ExportCredential,
    ExportCredentialLink,
    ExportHost,
    ImportRequest,
    ImportResponse,
    OpExport,
    OperationRead,
)
from services.activity import log_activity
from ws_manager import broadcast_sync

router = APIRouter()


# ─── Export ───────────────────────────────────────────────────────────────────

@router.get("/ops/{op_id}/export")
def export_op(op_id: str, db: Session = Depends(get_db)):
    op = db.get(Operation, op_id)
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")

    hosts = (
        db.query(Host)
        .options(selectinload(Host.ips), selectinload(Host.users))
        .filter(Host.op_id == op_id)
        .all()
    )
    credentials = db.query(Credential).filter(Credential.op_id == op_id).all()

    credential_ids = {c.id for c in credentials}
    cred_links = (
        db.query(CredentialLink)
        .filter(CredentialLink.credential_id.in_(credential_ids))
        .all()
        if credential_ids else []
    )

    connections = db.query(ConnectionRecord).filter(ConnectionRecord.op_id == op_id).all()
    activity = (
        db.query(ActivityLog)
        .filter(ActivityLog.op_id == op_id)
        .order_by(ActivityLog.created_at.asc())
        .all()
    )

    export_data = OpExport(
        exported_at=datetime.now(timezone.utc),
        operation=OperationRead.model_validate(op),
        hosts=[ExportHost.model_validate(h) for h in hosts],
        credentials=[ExportCredential.model_validate(c) for c in credentials],
        credential_links=[ExportCredentialLink.model_validate(link) for link in cred_links],
        connections=[ExportConnection.model_validate(c) for c in connections],
        activity_log=[ExportActivityEntry.model_validate(a) for a in activity],
    )

    safe_name = re.sub(r"[^a-z0-9_\-]", "_", op.name.lower())[:40]
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"lockpick-{safe_name}-{date_str}.json"

    response = JSONResponse(
        content=export_data.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
    return response


# ─── Import ───────────────────────────────────────────────────────────────────

@router.post("/ops/import", response_model=ImportResponse, status_code=201)
def import_op(body: ImportRequest, db: Session = Depends(get_db)):
    src = body.data
    new_op_name = body.name_override or f"{src.operation.name} (imported)"

    # Build a full ID remap — old UUID → new UUID
    id_map: dict[str, str] = {}

    def remap(old_id: str | None) -> str | None:
        if old_id is None:
            return None
        if old_id not in id_map:
            id_map[old_id] = str(uuid.uuid4())
        return id_map[old_id]

    # Pre-register all entity IDs so forward-references resolve correctly
    all_old_ids = (
        [src.operation.id]
        + [h.id for h in src.hosts]
        + [ip.id for h in src.hosts for ip in h.ips]
        + [u.id for h in src.hosts for u in h.users]
        + [c.id for c in src.credentials]
        + [link.id for link in src.credential_links]
        + [c.id for c in src.connections]
        + [a.id for a in src.activity_log]
    )
    for old_id in all_old_ids:
        remap(old_id)

    new_op_id = id_map[src.operation.id]

    # 1. Operation
    op = Operation(
        id=new_op_id,
        name=new_op_name,
        description=src.operation.description,
        created_at=src.operation.created_at,
    )
    db.add(op)

    # 2. Hosts + IPs + Users
    for h in src.hosts:
        host = Host(
            id=remap(h.id),
            op_id=new_op_id,
            nickname=h.nickname,
            comment=h.comment,
            status=h.status,
            created_at=h.created_at,
        )
        db.add(host)
        for ip in h.ips:
            db.add(HostIP(
                id=remap(ip.id),
                host_id=remap(h.id),
                ip_address=ip.ip_address,
                source=ip.source,
                addr_type=ip.addr_type,
                first_seen_at=ip.first_seen_at,
            ))
        for u in h.users:
            db.add(HostUser(
                id=remap(u.id),
                host_id=remap(h.id),
                username=u.username,
                shell=u.shell,
                home_dir=u.home_dir,
                source=u.source,
                created_at=u.created_at,
            ))

    # 3. Credentials
    for c in src.credentials:
        db.add(Credential(
            id=remap(c.id),
            op_id=new_op_id,
            cred_type=c.cred_type,
            name=c.name,
            value=c.value,
            fingerprint=c.fingerprint,
            key_type=c.key_type,
            passphrase=c.passphrase,
            comment=c.comment,
            created_at=c.created_at,
        ))

    # 4. Credential links
    for link in src.credential_links:
        db.add(CredentialLink(
            id=remap(link.id),
            credential_id=remap(link.credential_id),
            host_id=remap(link.host_id),
            username=link.username,
            host_user_id=remap(link.host_user_id),
            relationship_type=link.relationship_type,
            file_source=link.file_source,
        ))

    # 5. Connections
    for c in src.connections:
        db.add(ConnectionRecord(
            id=remap(c.id),
            op_id=new_op_id,
            src_host_id=remap(c.src_host_id),
            src_ip=c.src_ip,
            src_user=c.src_user,
            dst_host_id=remap(c.dst_host_id),
            dst_ip=c.dst_ip,
            dst_user=c.dst_user,
            connection_type=c.connection_type,
            direction_context=c.direction_context,
            auth_method=c.auth_method,
            credential_id=remap(c.credential_id),
            timestamp=c.timestamp,
            raw_line=c.raw_line,
            source_file=c.source_file,
            created_at=c.created_at,
        ))

    # 6. Activity log
    for a in src.activity_log:
        db.add(ActivityLog(
            id=remap(a.id),
            op_id=new_op_id,
            action=a.action,
            entity_type=a.entity_type,
            entity_id=remap(a.entity_id),
            detail=a.detail,
            created_at=a.created_at,
        ))

    log_activity(db, new_op_id, "op.import", "operation", entity_id=new_op_id)
    db.commit()
    broadcast_sync(new_op_id, {"type": "update", "entity_type": "operation", "op_id": new_op_id})
    return ImportResponse(op_id=new_op_id, op_name=new_op_name)
