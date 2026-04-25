"""Atomic host-merge service.

Moves all relations from a *source* `Host` onto a *target* `Host`, then
deletes the source row. Used by:

- Phase 15 manual merge (`POST /hosts/{source_id}/merge`).
- Phase 15 auto-merge from the upload pipeline's alias-conflict branch
  (when an alias collides with an unresolved host).

The helper does **not** call `db.commit()`, `log_activity()`, or
`broadcast_sync()` — the caller owns those (mirrors `process_single_file`,
Architecture Rule #20). Architecture Rule #23 fixes the dedup keys and
the relations-moved set; see AGENT.md.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session, selectinload

from models import (
    ConnectionRecord,
    Host,
    SshConfigPattern,
)

# Resolution tokens: any other string is treated as a free-text override
# for nickname / comment. `status` accepts only the two tokens.
_TOKEN_SOURCE = "source"
_TOKEN_TARGET = "target"


def _resolve_string_field(
    resolutions: dict, key: str, source_val: Optional[str], target_val: Optional[str]
) -> Optional[str]:
    """Return the merged value for a string field (nickname or comment)."""
    if key not in resolutions:
        return target_val
    choice = resolutions[key]
    if choice == _TOKEN_SOURCE:
        return source_val
    if choice == _TOKEN_TARGET:
        return target_val
    # Anything else is a free-text override.
    return choice


def merge_hosts(
    db: Session,
    op_id: str,
    source_id: str,
    target_id: str,
    resolutions: Optional[dict] = None,
) -> dict:
    """Move all relations from *source* host onto *target*; delete source.

    Caller owns the transaction — this helper flushes but does not commit.

    *resolutions* (all keys optional) controls how field-level conflicts are
    resolved on the target row:

    * ``"nickname"``: ``"source"``, ``"target"``, or any other string
      (used as a free-text override).
    * ``"comment"``: same shape as nickname.
    * ``"status"``: ``"source"`` or ``"target"`` only — status is an enum.

    Missing keys leave the target's existing value unchanged.

    Dedup keys (Architecture Rule #23):
    * ``HostIP``        — `(host_id, ip_address)`
    * ``CredentialLink``— `(credential_id, host_id, relationship_type, username)`
    Other relations (``HostUser``, ``SudoRule``) are NOT deduped.
    ``ConnectionRecord`` self-loops (src=dst=target after merge) are preserved.

    Returns::

        {
          "source_nickname": str,    # captured before delete
          "target_nickname": str,    # post-resolution
          "counts": {
            "ips_moved": int, "ips_deduped": int,
            "users_moved": int,
            "credential_links_moved": int, "credential_links_deduped": int,
            "connections_moved": int,
            "notes_moved": int,
            "ssh_patterns_moved": int,
            "sudo_rules_moved": int,
          },
        }

    Raises ``ValueError`` on bad inputs (same id, missing host, cross-op).
    """
    if source_id == target_id:
        raise ValueError("source and target must differ")

    # Eager-load every relationship we touch on BOTH sides. The target side
    # requires its own load because reassignments via back_populates
    # (`u.host = target`) need target's collection to be populated, and
    # several Host relationships are lazy="raise_on_sql".
    eager_opts = (
        selectinload(Host.ips),
        selectinload(Host.users),
        selectinload(Host.credential_links),
        selectinload(Host.notes),
        selectinload(Host.sudo_rules),
    )
    source = (
        db.query(Host).options(*eager_opts).filter(Host.id == source_id).first()
    )
    target = (
        db.query(Host).options(*eager_opts).filter(Host.id == target_id).first()
    )
    if source is None:
        raise ValueError(f"source host {source_id} not found")
    if target is None:
        raise ValueError(f"target host {target_id} not found")
    if source.op_id != op_id or target.op_id != op_id:
        raise ValueError("both hosts must belong to the given op")

    resolutions = resolutions or {}
    counts = {
        "ips_moved": 0, "ips_deduped": 0,
        "users_moved": 0,
        "credential_links_moved": 0, "credential_links_deduped": 0,
        "connections_moved": 0,
        "notes_moved": 0,
        "ssh_patterns_moved": 0,
        "sudo_rules_moved": 0,
    }
    source_nickname = source.nickname

    # ── 1. HostIP ── dedupe on ip_address (case-sensitive; resolver normalizes) ──
    # Deduped rows are NOT explicitly deleted — they stay attached to source
    # and ride the cascade="all, delete-orphan" wave when source itself is
    # deleted at the end. Calling db.delete() here in addition to the cascade
    # produced spurious "DELETE expected 1 row, matched 0" warnings.
    target_ips = {ip.ip_address for ip in target.ips}
    for ip in list(source.ips):
        if ip.ip_address in target_ips:
            counts["ips_deduped"] += 1
        else:
            ip.host = target
            target_ips.add(ip.ip_address)
            counts["ips_moved"] += 1

    # ── 2. HostUser ── re-point all; no dedup (per Decision §3) ──────────────────
    for user in list(source.users):
        user.host = target
        counts["users_moved"] += 1

    # ── 3. CredentialLink ── dedupe on (credential_id, relationship_type, username)
    # Same cascade-on-delete strategy as HostIP — deduped rows stay on source
    # and disappear with it.
    target_link_keys = {
        (lnk.credential_id, lnk.relationship_type, lnk.username)
        for lnk in target.credential_links
    }
    for link in list(source.credential_links):
        key = (link.credential_id, link.relationship_type, link.username)
        if key in target_link_keys:
            counts["credential_links_deduped"] += 1
        else:
            link.host = target
            target_link_keys.add(key)
            counts["credential_links_moved"] += 1

    # ── 4. HostNote ── re-point ──────────────────────────────────────────────────
    for note in list(source.notes):
        note.host = target
        counts["notes_moved"] += 1

    # ── 5. SudoRule ── re-point; no dedup ────────────────────────────────────────
    for rule in list(source.sudo_rules):
        rule.host = target
        counts["sudo_rules_moved"] += 1

    # ── 6. ConnectionRecord ── bulk update src and dst host refs ─────────────────
    src_count = (
        db.query(ConnectionRecord)
        .filter(ConnectionRecord.src_host_id == source_id)
        .update({"src_host_id": target_id}, synchronize_session=False)
    )
    dst_count = (
        db.query(ConnectionRecord)
        .filter(ConnectionRecord.dst_host_id == source_id)
        .update({"dst_host_id": target_id}, synchronize_session=False)
    )
    counts["connections_moved"] = int(src_count) + int(dst_count)

    # ── 7. SshConfigPattern ── bulk update source_host_id ────────────────────────
    pat_count = (
        db.query(SshConfigPattern)
        .filter(SshConfigPattern.source_host_id == source_id)
        .update({"source_host_id": target_id}, synchronize_session=False)
    )
    counts["ssh_patterns_moved"] = int(pat_count)

    # ── 8. Apply resolutions to target ───────────────────────────────────────────
    target.nickname = _resolve_string_field(
        resolutions, "nickname", source.nickname, target.nickname
    )
    target.comment = _resolve_string_field(
        resolutions, "comment", source.comment, target.comment
    )
    if resolutions.get("status") == _TOKEN_SOURCE:
        target.status = source.status
    # "target" or missing → leave target's status untouched.

    # ── 9. Delete source ─────────────────────────────────────────────────────────
    db.delete(source)
    db.flush()

    return {
        "source_nickname": source_nickname,
        "target_nickname": target.nickname,
        "counts": counts,
    }
