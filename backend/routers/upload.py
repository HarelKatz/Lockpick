"""File upload, listing, and serving endpoints.

POST /api/ops/{op_id}/upload      — parse and store an uploaded file
GET  /api/ops/{op_id}/uploads     — list all uploaded files for an op
GET  /api/ops/{op_id}/uploads/{safe_name} — serve a raw uploaded file

The heavy parsing logic lives in `services/upload_pipeline.py` (Architecture
Rule #20). This router is a thin wrapper that owns the HTTP contract:
validation, activity log, commit, and WS broadcast.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import (
    ConnectionRecord,
    Credential,
    CredentialLink,
    Host,
    Operation,
)
from parsers.registry import PARSER_REGISTRY
from schemas import UploadFileInfo
from services.activity import log_activity
from services.upload_pipeline import (
    _SAFE_NAME_OFFSET,
    _UUID_PREFIX_LEN,
    ParserCrashError,
    find_pivot_opportunities,
    process_single_file,
)
from ws_manager import broadcast_sync

log = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])


@router.post("/ops/{op_id}/upload")
async def upload_file(
    op_id: str,
    file: UploadFile = File(...),
    file_type: str = Form(...),
    host_id: str = Form(...),
    username: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Parse an uploaded file and insert the resulting records into the operation."""
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")

    host = db.query(Host).filter(Host.id == host_id, Host.op_id == op_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found in this operation")

    if file_type not in PARSER_REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file_type '{file_type}'. Supported: {sorted(PARSER_REGISTRY)}",
        )

    content = await file.read()
    filename = file.filename or file_type

    try:
        result = process_single_file(
            db=db,
            op_id=op_id,
            host_id=host_id,
            file_type=file_type,
            content=content,
            filename=filename,
            username=username,
        )
    except ParserCrashError as e:
        raise HTTPException(status_code=500, detail=f"Parser error: {e.original}")

    log_activity(
        db, op_id, "upload.parse", "upload",
        detail=(
            f"Parsed {file_type} file '{filename}': "
            f"{result['new_credentials']} creds, {result['new_credential_links']} links, "
            f"{result['new_connections']} connections, {result['new_hosts']} hosts, "
            f"{result['new_sudo_rules']} sudo rules, "
            f"{result['new_system_fields']} system fields"
        ),
    )
    # One activity entry per auto-merge that happened during parsing — gives
    # the operator a per-merge audit trail (Architecture Rule #23).
    for am in result["auto_merges"]:
        c = am["counts"]
        log_activity(
            db, op_id, "host.auto_merge", "host", entity_id=am["target_host_id"],
            detail=(
                f"Auto-merged '{am['source_nickname']}' into "
                f"'{am['target_nickname']}' via alias '{am['alias']}' "
                f"({c['ips_moved']} ips, {c['users_moved']} users, "
                f"{c['credential_links_moved']} cred links, "
                f"{c['connections_moved']} connections moved)"
            ),
        )
    db.commit()
    broadcast_sync(op_id, {"type": "update", "entity_type": "host", "op_id": op_id})

    pivot_messages = find_pivot_opportunities(db, op_id, result["fingerprints"])

    return {
        "ok": True,
        "filename": filename,
        "file_type": file_type,
        "stats": result["stats"],
        "summary": {
            "new_credentials": result["new_credentials"],
            "new_credential_links": result["new_credential_links"],
            "new_connections": result["new_connections"],
            "new_hosts": result["new_hosts"],
            "new_sudo_rules": result["new_sudo_rules"],
            "warnings": result["warnings"],
            "merge_candidates": result["merge_candidates"],
        },
        "pivot_opportunities": pivot_messages,
    }


# ─── List uploaded files ──────────────────────────────────────────────────────

@router.get("/ops/{op_id}/uploads", response_model=list[UploadFileInfo])
def list_uploads(op_id: str, db: Session = Depends(get_db)):
    """List all raw files uploaded for an op, enriched with host associations."""
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")

    op_upload_dir = Path(settings.upload_path) / op_id
    if not op_upload_dir.is_dir():
        return []

    # Build reverse maps: safe_name → set of host_ids
    link_hosts: dict[str, set[str]] = {}
    conn_hosts: dict[str, set[str]] = {}

    for link in (
        db.query(CredentialLink)
        .join(Credential, CredentialLink.credential_id == Credential.id)
        .filter(Credential.op_id == op_id)
        .all()
    ):
        if link.file_source:
            link_hosts.setdefault(link.file_source, set()).add(link.host_id)

    for conn in (
        db.query(ConnectionRecord)
        .filter(ConnectionRecord.op_id == op_id)
        .all()
    ):
        if conn.source_file:
            conn_hosts.setdefault(conn.source_file, set()).add(
                conn.src_host_id or conn.dst_host_id or ""
            )

    results: list[UploadFileInfo] = []
    for entry in sorted(op_upload_dir.iterdir()):
        if not entry.is_file():
            continue
        safe_name = entry.name
        original_name = safe_name[_SAFE_NAME_OFFSET:] if len(safe_name) > _SAFE_NAME_OFFSET and safe_name[_UUID_PREFIX_LEN] == "_" else safe_name
        stat = entry.stat()
        host_ids = list(
            (link_hosts.get(safe_name, set()) | conn_hosts.get(safe_name, set()))
            - {""}
        )
        results.append(UploadFileInfo(
            safe_name=safe_name,
            original_name=original_name,
            size_bytes=stat.st_size,
            host_ids=host_ids,
            uploaded_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        ))

    results.sort(key=lambda f: f.uploaded_at)
    return results


# ─── Serve a raw uploaded file ────────────────────────────────────────────────

@router.get("/ops/{op_id}/uploads/{safe_name}")
def get_upload(
    op_id: str,
    safe_name: str,
    download: bool = Query(False, description="Set true to force Content-Disposition: attachment"),
    db: Session = Depends(get_db),
):
    """Serve a raw uploaded file for viewing or download."""
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")

    if "/" in safe_name or "\\" in safe_name or ".." in safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = Path(settings.upload_path) / op_id / safe_name
    try:
        file_path.resolve().relative_to(Path(settings.upload_path).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    original_name = safe_name[_SAFE_NAME_OFFSET:] if len(safe_name) > _SAFE_NAME_OFFSET and safe_name[_UUID_PREFIX_LEN] == "_" else safe_name

    disposition = "attachment" if download else "inline"
    return FileResponse(
        path=str(file_path),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{original_name}"',
        },
    )
