"""GET /ops/{op_id}/search?q= — global search across all op data."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import (
    ConnectionRecord,
    Credential,
    Host,
    HostIP,
    HostUser,
    Operation,
)
from schemas import SearchResponse, SearchResult

router = APIRouter()

_MAX_PER_TYPE = 100


@router.get("/ops/{op_id}/search", response_model=SearchResponse)
def search_op(
    op_id: str,
    q: str = Query(min_length=2, description="Search query (minimum 2 characters)"),
    db: Session = Depends(get_db),
):
    if not db.get(Operation, op_id):
        raise HTTPException(status_code=404, detail="Operation not found")

    pattern = f"%{q}%"
    results: List[SearchResult] = []

    # ── Hosts ──────────────────────────────────────────────────────────────────
    for host in (
        db.query(Host)
        .filter(
            Host.op_id == op_id,
            (Host.nickname.ilike(pattern) | Host.comment.ilike(pattern)),
        )
        .limit(_MAX_PER_TYPE)
        .all()
    ):
        for field, val in (("nickname", host.nickname), ("comment", host.comment)):
            if val and q.lower() in val.lower():
                results.append(SearchResult(
                    type="host",
                    host_id=host.id,
                    nickname=host.nickname,
                    matched_field=field,
                    snippet=val,
                ))
                break  # one result per host

    # ── Host IPs ───────────────────────────────────────────────────────────────
    for ip in (
        db.query(HostIP)
        .join(Host, HostIP.host_id == Host.id)
        .filter(Host.op_id == op_id, HostIP.ip_address.ilike(pattern))
        .limit(_MAX_PER_TYPE)
        .all()
    ):
        host = db.get(Host, ip.host_id)
        results.append(SearchResult(
            type="host_ip",
            host_id=ip.host_id,
            nickname=host.nickname if host else None,
            matched_field="ip_address",
            snippet=ip.ip_address,
        ))

    # ── Host Users ─────────────────────────────────────────────────────────────
    for user in (
        db.query(HostUser)
        .join(Host, HostUser.host_id == Host.id)
        .filter(Host.op_id == op_id, HostUser.username.ilike(pattern))
        .limit(_MAX_PER_TYPE)
        .all()
    ):
        host = db.get(Host, user.host_id)
        results.append(SearchResult(
            type="host_user",
            host_id=user.host_id,
            nickname=host.nickname if host else None,
            matched_field="username",
            snippet=user.username,
        ))

    # ── Credentials ────────────────────────────────────────────────────────────
    for cred in (
        db.query(Credential)
        .filter(
            Credential.op_id == op_id,
            (
                Credential.name.ilike(pattern)
                | Credential.comment.ilike(pattern)
                | Credential.fingerprint.ilike(pattern)
            ),
        )
        .limit(_MAX_PER_TYPE)
        .all()
    ):
        for field, val in (
            ("name", cred.name),
            ("comment", cred.comment),
            ("fingerprint", cred.fingerprint),
        ):
            if val and q.lower() in val.lower():
                results.append(SearchResult(
                    type="credential",
                    credential_id=cred.id,
                    matched_field=field,
                    snippet=val,
                ))
                break

    # ── Connections ────────────────────────────────────────────────────────────
    for conn in (
        db.query(ConnectionRecord)
        .filter(
            ConnectionRecord.op_id == op_id,
            (
                ConnectionRecord.src_ip.ilike(pattern)
                | ConnectionRecord.dst_ip.ilike(pattern)
                | ConnectionRecord.src_user.ilike(pattern)
                | ConnectionRecord.dst_user.ilike(pattern)
                | ConnectionRecord.raw_line.ilike(pattern)
            ),
        )
        .limit(_MAX_PER_TYPE)
        .all()
    ):
        for field, val in (
            ("src_ip", conn.src_ip),
            ("dst_ip", conn.dst_ip),
            ("src_user", conn.src_user),
            ("dst_user", conn.dst_user),
            ("raw_line", conn.raw_line),
        ):
            if val and q.lower() in val.lower():
                results.append(SearchResult(
                    type="connection",
                    connection_id=conn.id,
                    matched_field=field,
                    snippet=val[:200] if len(val) > 200 else val,
                ))
                break

    return SearchResponse(query=q, results=results, total=len(results))
