"""Shared file-ingest pipeline used by both the single-file upload endpoint
and the bulk archive import endpoint.

The module exposes `process_single_file()`, which parses one file's bytes
and persists all resulting records (Hosts, HostUsers, Credentials,
CredentialLinks, ConnectionRecords, SshConfigPatterns, SudoRules) with the
same dedup semantics as the original upload handler.

The helper does **not** call `log_activity()`, `db.commit()`, or
`broadcast_sync()` — the caller owns those, so that an archive import can
emit one activity entry and one broadcast for a batch of files instead of
one per file.

See Architecture Rule #20.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from config import settings
from models import (
    Credential,
    CredentialLink,
    ConnectionRecord,
    Host,
    HostIP,
    HostUser,
    SshConfigPattern,
    SudoRule,
    _now,
    _uuid,
)
from parsers import UploadMetadata
from parsers.registry import PARSER_REGISTRY
from services.host_merge import merge_hosts
from services.ip_resolver import (
    _infer_addr_type,
    _is_routable_address,
    is_unresolved_host,
    resolve_ip,
)
from services.key_utils import infer_key_info
from services.ssh_pattern import ssh_match

log = logging.getLogger(__name__)

# Safe-name convention: `<uuid4>_<original_filename>`. UUID is 36 chars, then
# a single underscore separator. The listing and serving endpoints strip this
# prefix to recover the original filename.
_UUID_PREFIX_LEN = 36
_SAFE_NAME_OFFSET = 37

_LOOPBACK_EXACT = {"127.0.0.1", "::1", "localhost"}


class ParserCrashError(Exception):
    """Raised when a parser's parse() method throws an exception.

    Parsers are supposed to never crash (see CLAUDE.md parser guidelines).
    If one does, callers decide how to surface it: the single-file upload
    endpoint re-raises as HTTP 500; the archive import endpoint records it
    as a per-file warning and continues.
    """

    def __init__(self, parser_cls_name: str, original: Exception):
        super().__init__(f"Parser {parser_cls_name} crashed: {original}")
        self.parser_cls_name = parser_cls_name
        self.original = original


def _is_loopback(ip: str) -> bool:
    return ip in _LOOPBACK_EXACT or ip.startswith("127.")


def _get_or_create_host_user(
    db: Session, host_id: str, username: str,
    shell: Optional[str], home_dir: Optional[str], source: str,
) -> HostUser:
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


def _resolve_ip_side(
    db: Session,
    op_id: str,
    raw_ip: str,
    upload_host_ip: str,
    upload_host_id: str,
) -> tuple[str, Optional[str]]:
    """Resolve one ConnectionData IP to (resolved_ip, host_id).

    The ``__upload_host__`` sentinel and loopback addresses are both mapped
    to the upload host (loopback = "this machine" = the file's source host).
    The caller is responsible for deciding whether the resolved host is new
    (see `process_single_file`'s existing-id set).
    """
    if raw_ip == "__upload_host__" or _is_loopback(raw_ip):
        return upload_host_ip, upload_host_id
    resolved_host_id = resolve_ip(db, op_id, raw_ip, create_if_missing=True)
    return raw_ip, resolved_host_id


def find_pivot_opportunities(
    db: Session, op_id: str, new_fingerprints: list[str]
) -> list[str]:
    """Return human-readable pivot messages for keys that match authorized_keys elsewhere."""
    messages: list[str] = []
    for fp in new_fingerprints:
        all_creds = (
            db.query(Credential)
            .filter(Credential.op_id == op_id, Credential.fingerprint == fp)
            .options(selectinload(Credential.links))
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

        link_host_ids = {lnk.host_id for lnk in found_on + auth_keys}
        link_host_map = (
            {h.id: h for h in db.query(Host).filter(Host.id.in_(link_host_ids)).all()}
            if link_host_ids else {}
        )
        for src in found_on:
            for dst in auth_keys:
                src_host = link_host_map.get(src.host_id)
                dst_host = link_host_map.get(dst.host_id)
                if src_host and dst_host and src_host.id != dst_host.id:
                    src_label = f"{src_host.nickname}({src.username or '?'})"
                    dst_label = f"{dst_host.nickname}({dst.username or '?'})"
                    messages.append(
                        f"New pivot opportunity: {src_label} → {dst_label} via key {fp}"
                    )
    return messages


def process_single_file(
    db: Session,
    op_id: str,
    host_id: str,
    file_type: str,
    content: bytes,
    filename: str,
    username: Optional[str] = None,
) -> dict:
    """Parse one file's bytes and persist all resulting records.

    Does NOT call `log_activity()`, `db.commit()`, or `broadcast_sync()` —
    the caller owns those. The caller is also responsible for validating
    that `op_id` and `host_id` refer to existing rows (the helper assumes
    the host exists in the given op).

    Raises `ParserCrashError` if the parser itself throws an exception.

    Returns a dict with per-file counters and a `warnings` list. The
    `warnings` list carries BOTH parser-generated entries (`ParseResult.
    warnings`) AND pipeline-generated entries (e.g. alias-conflict skips
    from 1b). Callers should not assume a particular source — these are
    all operator-visible messages.
    """
    if file_type not in PARSER_REGISTRY:
        return {
            "ok": False,
            "filename": filename,
            "file_type": file_type,
            "stats": {},
            "new_credentials": 0,
            "new_credential_links": 0,
            "new_connections": 0,
            "new_hosts": 0,
            "new_sudo_rules": 0,
            "warnings": [f"Unsupported file type '{file_type}'; skipped"],
            "merge_candidates": [],
            "auto_merges": [],
            "fingerprints": [],
            "safe_name": "",
        }

    # Save raw file — unconditional, even if parser crashes (debugging aid).
    op_upload_dir = os.path.join(settings.upload_path, op_id)
    os.makedirs(op_upload_dir, exist_ok=True)
    safe_name = f"{_uuid()}_{filename}"
    raw_path = os.path.join(op_upload_dir, safe_name)
    try:
        with open(raw_path, "wb") as fh:
            fh.write(content)
    except OSError as e:
        log.warning("Failed to save raw upload %s: %s", raw_path, e)
        # Keep the UUID-prefixed safe_name so CredentialLink / ConnectionRecord
        # file_source references remain consistent even when disk write fails.

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
        raise ParserCrashError(parser_cls.__name__, e)

    # Resolve the upload host's preferred IP for substituting __upload_host__ /
    # loopback in connection records. Fall back to nickname when no IP known.
    host = db.query(Host).filter(Host.id == host_id).first()
    host_ip_row = db.query(HostIP).filter(HostIP.host_id == host_id).first()
    if host_ip_row:
        upload_host_ip = host_ip_row.ip_address
    elif host:
        upload_host_ip = host.nickname
    else:
        upload_host_ip = host_id  # pathological — caller should have validated

    # ── 1. HostUser records ───────────────────────────────────────────────
    if file_type == "authorized_keys":
        user_source = "authorized_keys"
    elif file_type in ("passwd", "shadow"):
        user_source = "passwd_file"
    else:
        user_source = "log_evidence"
    for (uname, shell, home_dir) in result.host_users_found:
        _get_or_create_host_user(db, host_id, uname, shell, home_dir, user_source)

    # ── 1b. Discovered hosts (nmap, etc_hosts, …) ────────────────────────
    # Snapshot existing host ids so we can tell "new vs resolved-to-existing"
    # for the new_hosts counter. Every time resolve_ip creates a new host
    # we add its id to this set so subsequent iterations within the same
    # file don't double-count.
    existing_host_ids: set[str] = {
        hid for (hid,) in db.query(Host.id).filter(Host.op_id == op_id).all()
    }
    # Warnings produced by the pipeline itself (vs. parser-generated
    # `result.warnings`). Merged into the returned warnings list.
    helper_warnings: list[str] = []
    # Structured records of pipeline-level events for the caller to log/render:
    # `auto_merges` describes silent host collapses that happened during
    # this file (one per merge); `merge_candidates` is what the operator
    # could merge manually (alias conflict where the colliding host wasn't
    # safe to dissolve).
    auto_merges: list[dict] = []
    merge_candidates: list[dict] = []
    new_hosts = 0
    for hd in result.hosts_found:
        resolved_id = resolve_ip(db, op_id, hd.ip_address, create_if_missing=True)
        if not resolved_id:
            continue
        if resolved_id not in existing_host_ids:
            new_hosts += 1
            existing_host_ids.add(resolved_id)
        if hd.nickname:
            resolved_host = (
                db.query(Host)
                .options(
                    selectinload(Host.users),
                    selectinload(Host.credential_links),
                    selectinload(Host.notes),
                    selectinload(Host.sudo_rules),
                )
                .filter(Host.id == resolved_id)
                .first()
            )
            if resolved_host and is_unresolved_host(resolved_host):
                resolved_host.nickname = hd.nickname

        # Aliases: additional identifiers (IPs / hostnames) for the same
        # host. Add each as a HostIP on the resolved host, unless it:
        #   - is non-routable (multicast, garbage, spaces, etc.),
        #   - already points to a different host (Phase 15 host-merge
        #     will handle conflict resolution; silently merging here would
        #     be destructive),
        #   - is already a HostIP on our host.
        seen_aliases: set[str] = set()
        for alias in hd.aliases:
            alias = alias.strip()
            if not alias or alias in seen_aliases:
                continue
            seen_aliases.add(alias)
            if not _is_routable_address(alias):
                continue
            existing = resolve_ip(db, op_id, alias, create_if_missing=False)
            if existing is not None:
                if existing != resolved_id:
                    # Conflict: alias is bound to a different host. Two
                    # possible resolutions:
                    # (a) `existing` is a parser-created placeholder with
                    #     no operator content, AND it isn't the upload
                    #     host — silently merge it into resolved_id.
                    # (b) Otherwise, surface as a manual merge candidate.
                    auto_merged = False
                    if existing != host_id:
                        existing_host = (
                            db.query(Host)
                            .options(
                                selectinload(Host.users),
                                selectinload(Host.credential_links),
                                selectinload(Host.notes),
                                selectinload(Host.sudo_rules),
                            )
                            .filter(Host.id == existing)
                            .first()
                        )
                        if existing_host and is_unresolved_host(existing_host):
                            merge_result = merge_hosts(
                                db, op_id,
                                source_id=existing,
                                target_id=resolved_id,
                                resolutions=None,
                            )
                            auto_merges.append({
                                "source_host_id": existing,
                                "target_host_id": resolved_id,
                                "source_nickname": merge_result["source_nickname"],
                                "target_nickname": merge_result["target_nickname"],
                                "alias": alias,
                                "counts": merge_result["counts"],
                            })
                            helper_warnings.append(
                                f"Auto-merged unresolved host "
                                f"'{merge_result['source_nickname']}' into "
                                f"'{merge_result['target_nickname']}' via alias '{alias}'"
                            )
                            existing_host_ids.discard(existing)
                            auto_merged = True
                    if not auto_merged:
                        helper_warnings.append(
                            f"Alias '{alias}' already bound to another host; skipped "
                            f"(potential merge candidate with host {existing})"
                        )
                        merge_candidates.append({
                            "alias": alias,
                            "conflicting_host_id": existing,
                        })
                # else: alias already on our host — no-op, no warning.
                continue
            db.add(HostIP(
                id=_uuid(),
                host_id=resolved_id,
                ip_address=alias,
                addr_type=_infer_addr_type(alias),
                source="parsed",
                first_seen_at=_now(),
            ))
        if seen_aliases:
            db.flush()

    # ── 2. Credentials + CredentialLinks ─────────────────────────────────
    all_fingerprints: list[str] = []
    new_creds = 0
    new_links = 0

    for cred_data in result.credentials_found:
        key_type, fingerprint = infer_key_info(cred_data.value)

        existing_cred: Optional[Credential] = None
        if fingerprint:
            existing_cred = (
                db.query(Credential)
                .filter(Credential.op_id == op_id, Credential.fingerprint == fingerprint)
                .first()
            )
            all_fingerprints.append(fingerprint)

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

    # ── 3. ConnectionRecords ─────────────────────────────────────────────
    new_connections = 0

    for conn_data in result.connections_found:
        src_ip, src_host_id = _resolve_ip_side(
            db, op_id, conn_data.src_ip, upload_host_ip, host_id
        )
        dst_ip, dst_host_id = _resolve_ip_side(
            db, op_id, conn_data.dst_ip, upload_host_ip, host_id
        )
        for hid in (src_host_id, dst_host_id):
            if hid and hid not in existing_host_ids:
                new_hosts += 1
                existing_host_ids.add(hid)

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

    # ── 4. SSH config patterns ───────────────────────────────────────────
    for pat_data in result.patterns_found:
        pattern_str = " ".join(pat_data.aliases)

        candidates = (
            db.query(Host)
            .options(selectinload(Host.ips))
            .filter(Host.op_id == op_id, Host.id != host_id)
            .all()
        )
        for candidate in candidates:
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

        db.add(SshConfigPattern(
            id=_uuid(),
            op_id=op_id,
            source_host_id=host_id,
            pattern=pattern_str,
            username=pat_data.username,
            created_at=_now(),
        ))

    # ── 5. SudoRule records ──────────────────────────────────────────────
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

    return {
        "ok": True,
        "filename": filename,
        "file_type": file_type,
        "stats": result.stats,
        "new_credentials": new_creds,
        "new_credential_links": new_links,
        "new_connections": new_connections,
        "new_hosts": new_hosts,
        "new_sudo_rules": new_sudo_rules,
        "warnings": list(result.warnings) + helper_warnings,
        "merge_candidates": merge_candidates,
        "auto_merges": auto_merges,
        "fingerprints": all_fingerprints,
        "safe_name": safe_name,
    }
