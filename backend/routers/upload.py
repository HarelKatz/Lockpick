"""File upload, listing, and serving endpoints.

POST /api/ops/{op_id}/upload      — parse and store an uploaded file
GET  /api/ops/{op_id}/uploads     — list all uploaded files for an op
GET  /api/ops/{op_id}/uploads/{safe_name} — serve a raw uploaded file
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import (
    Credential,
    CredentialLink,
    ConnectionRecord,
    Host,
    HostIP,
    HostUser,
    Operation,
    SshConfigPattern,
    SudoRule,
)
from parsers import UploadMetadata
from parsers.registry import PARSER_REGISTRY
from schemas import UploadFileInfo
from services.activity import log_activity
from services.ip_resolver import resolve_ip
from services.key_utils import infer_key_info
from services.ssh_pattern import ssh_match
from ws_manager import broadcast_sync

log = logging.getLogger(__name__)

_UUID_PREFIX_LEN = 36   # UUID is 36 chars
_SAFE_NAME_OFFSET = 37  # UUID + underscore separator

router = APIRouter(tags=["upload"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def _get_or_create_host_user(
    db: Session, host_id: str, username: str,
    shell: Optional[str], home_dir: Optional[str], source: str
) -> HostUser:
    """Return existing HostUser or create a new one. Updates shell/home_dir if provided."""
    hu = (
        db.query(HostUser)
        .filter(HostUser.host_id == host_id, HostUser.username == username)
        .first()
    )
    if hu:
        if shell and not hu.shell:
            hu.shell = shell
        if home_dir and not hu.home_dir:
            hu.home_dir = home_dir
        return hu
    hu = HostUser(
        id=_uuid(),
        host_id=host_id,
        username=username,
        shell=shell,
        home_dir=home_dir,
        source=source,
        created_at=_now(),
    )
    db.add(hu)
    db.flush()
    return hu


_LOOPBACK_EXACT = {"127.0.0.1", "::1", "localhost"}


def _is_loopback(ip: str) -> bool:
    return ip in _LOOPBACK_EXACT or ip.startswith("127.")


def _resolve_ip_side(
    db: Session,
    op_id: str,
    raw_ip: str,
    upload_host_ip: str,
    upload_host_id: str,
) -> tuple[str, Optional[str], bool]:
    """Resolve one ConnectionData IP to (resolved_ip, host_id, is_new_auto_host).

    The ``__upload_host__`` sentinel and loopback addresses are both mapped to
    the upload host (loopback = "this machine" = the file's source host).
    For any other IP, resolve_ip is called with create_if_missing=True and the
    returned boolean indicates whether a *new* auto-created host was added.
    """
    if raw_ip == "__upload_host__" or _is_loopback(raw_ip):
        return upload_host_ip, upload_host_id, False
    resolved_host_id = resolve_ip(db, op_id, raw_ip, create_if_missing=True)
    is_new = False
    if resolved_host_id and resolved_host_id != upload_host_id:
        h = db.query(Host).filter(Host.id == resolved_host_id).first()
        if h and h.comment and "Auto-created" in h.comment:
            is_new = True
    return raw_ip, resolved_host_id, is_new


def _find_pivot_opportunities(
    db: Session, op_id: str, new_fingerprints: list[str]
) -> list[str]:
    """Return human-readable pivot messages for newly added keys that match authorized_keys elsewhere."""
    messages = []
    for fp in new_fingerprints:
        cred = (
            db.query(Credential)
            .filter(Credential.op_id == op_id, Credential.fingerprint == fp)
            .first()
        )
        if not cred:
            continue
        # Collect all links across ALL creds with this fingerprint
        # (normally just one Credential due to dedup, but may be multiple)
        all_creds = (
            db.query(Credential)
            .filter(Credential.op_id == op_id, Credential.fingerprint == fp)
            .all()
        )
        found_on = []
        auth_keys = []
        for c in all_creds:
            for link in c.links:
                if link.relationship_type == "found_on_disk":
                    found_on.append(link)
                elif link.relationship_type == "authorized_key":
                    auth_keys.append(link)

        for src in found_on:
            for dst in auth_keys:
                src_host = db.query(Host).filter(Host.id == src.host_id).first()
                dst_host = db.query(Host).filter(Host.id == dst.host_id).first()
                if src_host and dst_host and src_host.id != dst_host.id:
                    src_label = f"{src_host.nickname}({src.username or '?'})"
                    dst_label = f"{dst_host.nickname}({dst.username or '?'})"
                    messages.append(
                        f"New pivot opportunity: {src_label} → {dst_label} via key {fp}"
                    )
    return messages


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
    # Validate op and host exist
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

    # Save raw file to uploads directory
    op_upload_dir = os.path.join(settings.upload_path, op_id)
    os.makedirs(op_upload_dir, exist_ok=True)
    safe_name = f"{_uuid()}_{filename}"
    raw_path = os.path.join(op_upload_dir, safe_name)
    try:
        with open(raw_path, "wb") as fh:
            fh.write(content)
    except OSError as e:
        log.warning("Failed to save raw upload %s: %s", raw_path, e)
        # Do not revert safe_name — keep the UUID-prefixed value so that any
        # CredentialLink / ConnectionRecord file_source references remain consistent.

    metadata = UploadMetadata(
        op_id=op_id,
        host_id=host_id,
        file_type=file_type,
        username=username,
        filename=filename,
    )

    parser_cls = PARSER_REGISTRY[file_type]
    try:
        result = parser_cls().parse(content, metadata)
    except Exception as e:
        log.exception("Parser %s crashed", parser_cls.__name__)
        raise HTTPException(status_code=500, detail=f"Parser error: {e}")

    # Resolve the upload host IP (we know its host_id, get any IP for it)
    upload_host_ip: Optional[str] = None
    host_ip_row = db.query(HostIP).filter(HostIP.host_id == host_id).first()
    if host_ip_row:
        upload_host_ip = host_ip_row.ip_address
    else:
        upload_host_ip = host.nickname  # fallback to nickname

    # ── 1. Create HostUser records ────────────────────────────────────────────
    if file_type == "authorized_keys":
        user_source = "authorized_keys"
    elif file_type in ("passwd", "shadow"):
        user_source = "passwd_file"
    else:
        user_source = "log_evidence"
    for (uname, shell, home_dir) in result.host_users_found:
        _get_or_create_host_user(db, host_id, uname, shell, home_dir, user_source)

    # ── 1b. Persist discovered hosts (e.g. from nmap, etc_hosts) ─────────────
    new_hosts = 0
    new_discovered_hosts = 0
    for hd in result.hosts_found:
        resolved_id = resolve_ip(db, op_id, hd.ip_address, create_if_missing=True)
        if resolved_id:
            if hd.nickname:
                resolved_host = db.query(Host).filter(Host.id == resolved_id).first()
                if resolved_host and resolved_host.comment and "Auto-created" in resolved_host.comment:
                    resolved_host.nickname = hd.nickname
            new_discovered_hosts += 1
    new_hosts += new_discovered_hosts

    # ── 2. Insert Credentials + CredentialLinks ───────────────────────────────
    all_upload_fingerprints: list[str] = []  # all fps seen (new or existing)
    new_creds = 0
    new_links = 0

    for cred_data in result.credentials_found:
        key_type, fingerprint = infer_key_info(cred_data.value)

        # Dedup: find existing Credential with same fingerprint in this op
        existing_cred: Optional[Credential] = None
        if fingerprint:
            existing_cred = (
                db.query(Credential)
                .filter(Credential.op_id == op_id, Credential.fingerprint == fingerprint)
                .first()
            )

        if fingerprint:
            all_upload_fingerprints.append(fingerprint)

        if existing_cred:
            cred_obj = existing_cred
        else:
            cred_obj = Credential(
                id=_uuid(),
                op_id=op_id,
                cred_type=cred_data.cred_type,
                name=cred_data.name,
                value=cred_data.value,
                fingerprint=fingerprint,
                key_type=key_type,
                created_at=_now(),
            )
            db.add(cred_obj)
            db.flush()
            new_creds += 1

        # CredentialLink for this host
        link_username = cred_data.username or username
        hu = None
        if link_username:
            hu = _get_or_create_host_user(db, host_id, link_username, None, None, user_source)

        existing_link = db.query(CredentialLink).filter(
            CredentialLink.credential_id == cred_obj.id,
            CredentialLink.host_id == host_id,
            CredentialLink.relationship_type == cred_data.relationship_type,
            CredentialLink.username == link_username,
        ).first()
        if not existing_link:
            link = CredentialLink(
                id=_uuid(),
                credential_id=cred_obj.id,
                host_id=host_id,
                username=link_username,
                host_user_id=hu.id if hu else None,
                relationship_type=cred_data.relationship_type,
                file_source=safe_name,
            )
            db.add(link)
            new_links += 1

    # ── 3. Insert ConnectionRecords ───────────────────────────────────────────
    new_connections = 0

    for conn_data in result.connections_found:
        # Resolve src/dst IPs — replace __upload_host__ sentinel
        src_ip, src_host_id, src_new = _resolve_ip_side(
            db, op_id, conn_data.src_ip, upload_host_ip, host_id
        )
        dst_ip, dst_host_id, dst_new = _resolve_ip_side(
            db, op_id, conn_data.dst_ip, upload_host_ip, host_id
        )
        new_hosts += src_new + dst_new

        # Match fingerprint to existing Credential for confirmed confidence
        cred_id = None
        if conn_data.credential_fingerprint:
            cred_match = (
                db.query(Credential)
                .filter(
                    Credential.op_id == op_id,
                    Credential.fingerprint == conn_data.credential_fingerprint,
                )
                .first()
            )
            if cred_match:
                cred_id = cred_match.id

        # Parse timestamp
        ts = None
        if conn_data.timestamp:
            try:
                ts = datetime.fromisoformat(conn_data.timestamp)
            except ValueError:
                pass

        conn_rec = ConnectionRecord(
            id=_uuid(),
            op_id=op_id,
            src_host_id=src_host_id,
            src_ip=src_ip,
            src_user=conn_data.src_user,
            dst_host_id=dst_host_id,
            dst_ip=dst_ip,
            dst_user=conn_data.dst_user,
            connection_type=conn_data.connection_type,
            direction_context=conn_data.direction_context,
            auth_method=conn_data.auth_method,
            credential_id=cred_id,
            timestamp=ts,
            raw_line=conn_data.raw_line,
            source_file=safe_name,
            created_at=_now(),
        )
        db.add(conn_rec)
        new_connections += 1

    # ── 4. Process SSH config patterns ──────────────────────────────────────────
    for pat_data in result.patterns_found:
        pattern_str = " ".join(pat_data.aliases)

        # Match against all existing hosts in this op (excluding the upload host)
        for candidate in db.query(Host).filter(Host.op_id == op_id, Host.id != host_id).all():
            names = [candidate.nickname] + [ip.ip_address for ip in candidate.ips]
            if not any(ssh_match(n, pat_data.aliases) for n in names):
                continue
            dst_ip = candidate.ips[0].ip_address if candidate.ips else candidate.nickname
            raw = f"ssh_config pattern match: Host {pattern_str}"
            existing = db.query(ConnectionRecord).filter(
                ConnectionRecord.src_host_id == host_id,
                ConnectionRecord.dst_host_id == candidate.id,
                ConnectionRecord.raw_line == raw,
            ).first()
            if existing:
                continue
            db.add(ConnectionRecord(
                id=_uuid(),
                op_id=op_id,
                src_host_id=host_id,
                src_ip=upload_host_ip,
                src_user=pat_data.username,
                dst_host_id=candidate.id,
                dst_ip=dst_ip,
                connection_type="ssh",
                direction_context="from_src_logs",
                raw_line=raw,
                source_file=safe_name,
                created_at=_now(),
            ))
            new_connections += 1

        # Store for future hosts that match this pattern
        db.add(SshConfigPattern(
            id=_uuid(),
            op_id=op_id,
            source_host_id=host_id,
            pattern=pattern_str,
            username=pat_data.username,
            created_at=_now(),
        ))

    # ── 5. Persist SudoRule records ───────────────────────────────────────────
    new_sudo_rules = 0
    for sr in result.sudo_rules_found:
        db.add(SudoRule(
            host_id=host_id,
            op_id=op_id,
            subject=sr.subject,
            subject_type=sr.subject_type,
            run_as=sr.run_as,
            commands=sr.commands,
            nopasswd=sr.nopasswd,
            raw_line=sr.raw_line,
        ))
        new_sudo_rules += 1

    log_activity(db, op_id, "upload.parse", "upload",
                 detail=f"Parsed {file_type} file '{filename}': "
                        f"{new_creds} creds, {new_links} links, {new_connections} connections, "
                        f"{new_hosts} hosts, {new_sudo_rules} sudo rules")
    db.commit()
    broadcast_sync(op_id, {"type": "update", "entity_type": "host", "op_id": op_id})

    # ── 6. Check for new pivot opportunities ─────────────────────────────────
    pivot_messages = _find_pivot_opportunities(db, op_id, all_upload_fingerprints)

    return {
        "ok": True,
        "filename": filename,
        "file_type": file_type,
        "stats": result.stats,
        "summary": {
            "new_credentials": new_creds,
            "new_credential_links": new_links,
            "new_connections": new_connections,
            "new_hosts": new_hosts,
            "warnings": result.warnings,
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
        # Strip the UUID prefix (_UUID_PREFIX_LEN chars + underscore separator) to recover original filename
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

    # Sort by uploaded_at ascending
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

    # Path traversal guard
    if "/" in safe_name or "\\" in safe_name or ".." in safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = Path(settings.upload_path) / op_id / safe_name
    # Ensure resolved path stays within the expected directory
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
