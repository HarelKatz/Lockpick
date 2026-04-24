"""Collection script + bulk archive import endpoints.

GET  /api/ops/{op_id}/collection-script
     Serves the committed bash script byte-identical for every op.

POST /api/ops/{op_id}/hosts/{host_id}/import-archive
     Accepts a .tar.gz produced by the collection script, extracts it with
     strict path-traversal defense, and dispatches each file through the
     shared upload pipeline with a single commit + activity + broadcast.

See Architecture Rules #20, #21, #22.
"""
from __future__ import annotations

import json
import logging
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Host, Operation
from services.activity import log_activity
from services.upload_pipeline import (
    ParserCrashError,
    find_pivot_opportunities,
    process_single_file,
)
from ws_manager import broadcast_sync

log = logging.getLogger(__name__)

router = APIRouter(tags=["collection"])

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "collection_script" / "lockpick_collect.sh"
_ERR_SUFFIX = ".err"
_MANIFEST_NAME = "manifest.json"
_ERR_EXCERPT_LEN = 500


# ─── GET /ops/{op_id}/collection-script ──────────────────────────────────────

@router.get("/ops/{op_id}/collection-script")
def get_collection_script(op_id: str, db: Session = Depends(get_db)):
    """Return the static collection script. No op-specific content in body."""
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")

    body = _SCRIPT_PATH.read_text()
    return PlainTextResponse(
        body,
        media_type="text/x-shellscript",
        headers={"Content-Disposition": 'attachment; filename="lockpick_collect.sh"'},
    )


# ─── POST /ops/{op_id}/hosts/{host_id}/import-archive ────────────────────────

def _validate_tar_member(member: tarfile.TarInfo) -> Optional[str]:
    """Return an error string if the member is unsafe; else None.

    Rejects absolute paths, '..' components, symlinks, hardlinks, and
    devices. Regular files and directories are accepted.
    """
    name = member.name
    if name.startswith("/"):
        return f"absolute path member: {name!r}"
    # Normalize and check for parent traversal
    parts = Path(name).parts
    if any(p == ".." for p in parts):
        return f"parent-traversal member: {name!r}"
    if member.issym() or member.islnk():
        return f"symlink/hardlink member: {name!r}"
    if member.isdev() or member.isfifo():
        return f"device/fifo member: {name!r}"
    return None


def _parse_archived_name(basename: str) -> tuple[Optional[str], Optional[str]]:
    """Decode `<file_type>__<username>.<ext>` → (file_type, username or None).

    Returns (None, None) if the filename does not match the convention.
    """
    stem, _ext = os.path.splitext(basename)
    if "__" not in stem:
        return None, None
    file_type, _, username = stem.partition("__")
    if not file_type:
        return None, None
    return file_type, (username or None)


@router.post("/ops/{op_id}/hosts/{host_id}/import-archive")
async def import_archive(
    op_id: str,
    host_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Extract a collection tarball and dispatch each file through the upload pipeline."""
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")

    host = db.query(Host).filter(Host.id == host_id, Host.op_id == op_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="Host not found in this operation")

    body = await file.read()
    if len(body) > settings.archive_import_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Archive exceeds {settings.archive_import_max_bytes} byte limit",
        )

    with tempfile.TemporaryDirectory(prefix="lockpick_archive_") as td:
        tmpdir = Path(td)

        # Write tarball to disk so tarfile can open it with a real path
        archive_path = tmpdir / "incoming.tar.gz"
        archive_path.write_bytes(body)

        try:
            tf = tarfile.open(archive_path, mode="r:gz")
        except tarfile.TarError as e:
            raise HTTPException(status_code=400, detail=f"Invalid tarball: {e}")

        try:
            # Explicit pre-check for bad members — gives specific error messages
            # that the built-in `data` filter would abstract away.
            for member in tf.getmembers():
                err = _validate_tar_member(member)
                if err is not None:
                    raise HTTPException(status_code=400, detail=f"Unsafe archive: {err}")

            extract_dir = tmpdir / "extracted"
            extract_dir.mkdir()
            # Layered defense: Python's 'data' filter rejects unsafe members.
            tf.extractall(extract_dir, filter="data")
        finally:
            tf.close()

        # Gather all extracted files (recursive; ignore directories)
        all_files: list[Path] = [p for p in extract_dir.rglob("*") if p.is_file()]

        # Optional manifest (informational — we don't rely on it for dispatch)
        manifest: dict = {}
        manifest_path = extract_dir / _MANIFEST_NAME
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text())
            except json.JSONDecodeError as e:
                log.warning("Malformed manifest.json in archive: %s", e)

        # Build a basename → Path index for .err sibling lookup
        by_basename: dict[str, Path] = {p.name: p for p in all_files}

        per_file: list[dict] = []
        all_fingerprints: list[str] = []
        files_processed = 0
        files_skipped = 0
        totals = {
            "new_credentials": 0,
            "new_credential_links": 0,
            "new_connections": 0,
            "new_hosts": 0,
            "warnings": [],
        }

        for path in sorted(all_files):
            basename = path.name
            if basename == _MANIFEST_NAME:
                continue
            if basename.endswith(_ERR_SUFFIX):
                continue  # surfaced as sibling warning on the matching file

            file_type, username = _parse_archived_name(basename)
            entry: dict = {
                "filename": basename,
                "file_type": file_type or "",
                "username": username,
                "ok": False,
                "summary": {
                    "new_credentials": 0,
                    "new_credential_links": 0,
                    "new_connections": 0,
                    "new_hosts": 0,
                    "warnings": [],
                },
            }

            if file_type is None:
                entry["summary"]["warnings"].append(
                    f"Filename '{basename}' does not match <file_type>__<username>.<ext>; skipped"
                )
                per_file.append(entry)
                files_skipped += 1
                continue

            content = path.read_bytes()

            try:
                result = process_single_file(
                    db=db,
                    op_id=op_id,
                    host_id=host_id,
                    file_type=file_type,
                    content=content,
                    filename=basename,
                    username=username,
                )
            except ParserCrashError as e:
                entry["summary"]["warnings"].append(f"Parser crashed: {e.original}")
                per_file.append(entry)
                files_skipped += 1
                continue

            entry["ok"] = result["ok"]
            entry["summary"] = {
                "new_credentials": result["new_credentials"],
                "new_credential_links": result["new_credential_links"],
                "new_connections": result["new_connections"],
                "new_hosts": result["new_hosts"],
                "warnings": list(result["warnings"]),
            }

            # Surface .err sibling contents as a per-file warning
            err_sibling = by_basename.get(basename + _ERR_SUFFIX)
            if err_sibling is not None and err_sibling.is_file() and err_sibling.stat().st_size > 0:
                excerpt = err_sibling.read_bytes()[:_ERR_EXCERPT_LEN].decode("utf-8", errors="replace")
                entry["summary"]["warnings"].append(
                    f"stderr from collection for '{basename}': {excerpt}"
                )

            if result["ok"]:
                files_processed += 1
                all_fingerprints.extend(result["fingerprints"])
                totals["new_credentials"] += result["new_credentials"]
                totals["new_credential_links"] += result["new_credential_links"]
                totals["new_connections"] += result["new_connections"]
                totals["new_hosts"] += result["new_hosts"]
            else:
                files_skipped += 1

            per_file.append(entry)

        log_activity(
            db, op_id, "upload.archive_import", "upload",
            detail=(
                f"Imported archive '{file.filename or 'archive.tar.gz'}': "
                f"{files_processed} files, {files_skipped} skipped, "
                f"{totals['new_credentials']} creds, "
                f"{totals['new_credential_links']} links, "
                f"{totals['new_connections']} connections, "
                f"{totals['new_hosts']} hosts"
            ),
        )
        db.commit()
        broadcast_sync(op_id, {"type": "update", "entity_type": "host", "op_id": op_id})

        # Pivot scan runs post-commit so newly-added CredentialLinks are visible
        # to the query (matches single-file upload ordering; also required when
        # the session has autoflush disabled, as in tests).
        pivot_messages = find_pivot_opportunities(db, op_id, all_fingerprints)

    return {
        "ok": True,
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "totals": totals,
        "per_file": per_file,
        "pivot_opportunities": pivot_messages,
    }
