"""Unit tests for services/host_merge.merge_hosts()."""
import pytest
from sqlalchemy.orm import Session

from models import (
    ConnectionRecord,
    Credential,
    CredentialLink,
    Host,
    HostIP,
    HostNote,
    HostUser,
    Operation,
    SshConfigPattern,
    SudoRule,
)
from services.host_merge import merge_hosts


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _op(db: Session, name: str = "Test Op") -> Operation:
    op = Operation(name=name)
    db.add(op)
    db.flush()
    return op


def _host(db: Session, op_id: str, nickname: str, *, ip: str | None = None,
          comment: str | None = None, status: str | None = None) -> Host:
    h = Host(op_id=op_id, nickname=nickname, comment=comment, status=status)
    db.add(h)
    db.flush()
    if ip:
        db.add(HostIP(host_id=h.id, ip_address=ip, addr_type="ipv4", source="manual"))
        db.flush()
    return h


def _cred(db: Session, op_id: str, *, fingerprint: str = "fp:abc",
          cred_type: str = "private_key", value: str = "KEY") -> Credential:
    c = Credential(op_id=op_id, cred_type=cred_type, value=value, fingerprint=fingerprint)
    db.add(c)
    db.flush()
    return c


def _link(db: Session, cred_id: str, host_id: str, *, username: str = "root",
          relationship_type: str = "found_on_disk") -> CredentialLink:
    lk = CredentialLink(
        credential_id=cred_id, host_id=host_id,
        username=username, relationship_type=relationship_type,
    )
    db.add(lk)
    db.flush()
    return lk


# ─── Validation ───────────────────────────────────────────────────────────────

def test_self_merge_raises(db_session):
    op = _op(db_session)
    h = _host(db_session, op.id, "h1")
    with pytest.raises(ValueError, match="must differ"):
        merge_hosts(db_session, op.id, h.id, h.id)


def test_missing_source_raises(db_session):
    op = _op(db_session)
    h = _host(db_session, op.id, "h1")
    with pytest.raises(ValueError, match="not found"):
        merge_hosts(db_session, op.id, "deadbeef-source", h.id)


def test_missing_target_raises(db_session):
    op = _op(db_session)
    h = _host(db_session, op.id, "h1")
    with pytest.raises(ValueError, match="not found"):
        merge_hosts(db_session, op.id, h.id, "deadbeef-target")


def test_cross_op_raises(db_session):
    op_a = _op(db_session, "A")
    op_b = _op(db_session, "B")
    src = _host(db_session, op_a.id, "src")
    tgt = _host(db_session, op_b.id, "tgt")
    with pytest.raises(ValueError, match="same op|given op"):
        merge_hosts(db_session, op_a.id, src.id, tgt.id)


# ─── Happy path / counts ─────────────────────────────────────────────────────

def test_happy_path_moves_all_relations_and_deletes_source(db_session):
    op = _op(db_session)
    src = _host(db_session, op.id, "old-nickname", ip="10.0.0.5")
    tgt = _host(db_session, op.id, "kept", ip="10.0.0.6")

    db_session.add(HostUser(host_id=src.id, username="bob"))
    db_session.add(HostNote(op_id=op.id, host_id=src.id, content="src note"))
    db_session.add(SudoRule(
        host_id=src.id, op_id=op.id, subject="bob", subject_type="user",
        run_as="root", commands="ALL", nopasswd=False,
    ))
    db_session.add(SshConfigPattern(
        op_id=op.id, source_host_id=src.id, pattern="*.corp", username="root",
    ))
    cred = _cred(db_session, op.id)
    _link(db_session, cred.id, src.id)
    db_session.flush()

    result = merge_hosts(db_session, op.id, src.id, tgt.id)

    assert result["source_nickname"] == "old-nickname"
    assert result["target_nickname"] == "kept"
    assert result["counts"] == {
        "ips_moved": 1, "ips_deduped": 0,
        "users_moved": 1,
        "credential_links_moved": 1, "credential_links_deduped": 0,
        "connections_moved": 0,
        "notes_moved": 1,
        "ssh_patterns_moved": 1,
        "sudo_rules_moved": 1,
    }

    # Source is gone.
    assert db_session.query(Host).filter(Host.id == src.id).first() is None
    # Target now owns everything.
    assert db_session.query(HostIP).filter(HostIP.host_id == tgt.id).count() == 2
    assert db_session.query(HostUser).filter(HostUser.host_id == tgt.id).count() == 1
    assert db_session.query(CredentialLink).filter(CredentialLink.host_id == tgt.id).count() == 1
    assert db_session.query(HostNote).filter(HostNote.host_id == tgt.id).count() == 1
    assert db_session.query(SudoRule).filter(SudoRule.host_id == tgt.id).count() == 1
    assert (
        db_session.query(SshConfigPattern)
        .filter(SshConfigPattern.source_host_id == tgt.id).count() == 1
    )


# ─── Dedup: HostIP ───────────────────────────────────────────────────────────

def test_hostip_dedup_keeps_target_drops_source(db_session):
    op = _op(db_session)
    src = _host(db_session, op.id, "src", ip="10.0.0.5")
    tgt = _host(db_session, op.id, "tgt", ip="10.0.0.5")  # same IP

    result = merge_hosts(db_session, op.id, src.id, tgt.id)

    assert result["counts"]["ips_moved"] == 0
    assert result["counts"]["ips_deduped"] == 1
    # Target still has exactly one HostIP for 10.0.0.5.
    ips = db_session.query(HostIP).filter(HostIP.host_id == tgt.id).all()
    assert len(ips) == 1
    assert ips[0].ip_address == "10.0.0.5"


def test_hostip_partial_dedup(db_session):
    """Source has two IPs; one collides with target, one doesn't."""
    op = _op(db_session)
    src = _host(db_session, op.id, "src", ip="10.0.0.5")
    db_session.add(HostIP(host_id=src.id, ip_address="db1.corp",
                          source="parsed", addr_type="hostname"))
    tgt = _host(db_session, op.id, "tgt", ip="10.0.0.5")
    db_session.flush()

    result = merge_hosts(db_session, op.id, src.id, tgt.id)

    assert result["counts"]["ips_moved"] == 1
    assert result["counts"]["ips_deduped"] == 1
    addrs = sorted(
        ip.ip_address for ip in
        db_session.query(HostIP).filter(HostIP.host_id == tgt.id).all()
    )
    assert addrs == ["10.0.0.5", "db1.corp"]


# ─── Dedup: CredentialLink ───────────────────────────────────────────────────

def test_credlink_dedup_on_same_upload_key(db_session):
    """Two links with the same (cred, relationship_type, username) — source's is dropped."""
    op = _op(db_session)
    src = _host(db_session, op.id, "src")
    tgt = _host(db_session, op.id, "tgt")
    cred = _cred(db_session, op.id)
    _link(db_session, cred.id, src.id, username="root", relationship_type="found_on_disk")
    _link(db_session, cred.id, tgt.id, username="root", relationship_type="found_on_disk")
    db_session.flush()

    result = merge_hosts(db_session, op.id, src.id, tgt.id)

    assert result["counts"]["credential_links_moved"] == 0
    assert result["counts"]["credential_links_deduped"] == 1
    links = db_session.query(CredentialLink).filter(CredentialLink.host_id == tgt.id).all()
    assert len(links) == 1


def test_credlink_no_dedup_when_username_differs(db_session):
    """Same cred, same relationship_type, but different username → both survive."""
    op = _op(db_session)
    src = _host(db_session, op.id, "src")
    tgt = _host(db_session, op.id, "tgt")
    cred = _cred(db_session, op.id)
    _link(db_session, cred.id, src.id, username="bob", relationship_type="found_on_disk")
    _link(db_session, cred.id, tgt.id, username="alice", relationship_type="found_on_disk")
    db_session.flush()

    result = merge_hosts(db_session, op.id, src.id, tgt.id)

    assert result["counts"]["credential_links_moved"] == 1
    assert result["counts"]["credential_links_deduped"] == 0
    usernames = sorted(
        lnk.username for lnk in
        db_session.query(CredentialLink).filter(CredentialLink.host_id == tgt.id).all()
    )
    assert usernames == ["alice", "bob"]


# ─── HostUser keep-duplicates ────────────────────────────────────────────────

def test_hostuser_duplicates_preserved(db_session):
    """Per Decision §3: HostUsers are not deduped — both `bob` rows remain."""
    op = _op(db_session)
    src = _host(db_session, op.id, "src")
    tgt = _host(db_session, op.id, "tgt")
    db_session.add(HostUser(host_id=src.id, username="bob", shell="/bin/bash"))
    db_session.add(HostUser(host_id=tgt.id, username="bob", shell="/bin/zsh"))
    db_session.flush()

    result = merge_hosts(db_session, op.id, src.id, tgt.id)

    assert result["counts"]["users_moved"] == 1
    bob_rows = (
        db_session.query(HostUser)
        .filter(HostUser.host_id == tgt.id, HostUser.username == "bob").all()
    )
    assert len(bob_rows) == 2
    shells = sorted(u.shell for u in bob_rows)
    assert shells == ["/bin/bash", "/bin/zsh"]


# ─── ConnectionRecord ────────────────────────────────────────────────────────

def test_connection_records_bulk_repointed(db_session):
    op = _op(db_session)
    src = _host(db_session, op.id, "src", ip="10.0.0.5")
    tgt = _host(db_session, op.id, "tgt", ip="10.0.0.6")
    other = _host(db_session, op.id, "other", ip="10.0.0.7")

    # Three records: src→other, other→src, src→tgt (self-loop after merge).
    db_session.add(ConnectionRecord(
        op_id=op.id, src_host_id=src.id, dst_host_id=other.id,
        src_ip="10.0.0.5", dst_ip="10.0.0.7",
        connection_type="ssh", direction_context="from_src_logs",
        source_file="x",
    ))
    db_session.add(ConnectionRecord(
        op_id=op.id, src_host_id=other.id, dst_host_id=src.id,
        src_ip="10.0.0.7", dst_ip="10.0.0.5",
        connection_type="ssh", direction_context="from_dst_logs",
        source_file="x",
    ))
    db_session.add(ConnectionRecord(
        op_id=op.id, src_host_id=src.id, dst_host_id=tgt.id,
        src_ip="10.0.0.5", dst_ip="10.0.0.6",
        connection_type="ssh", direction_context="from_src_logs",
        source_file="x",
    ))
    db_session.flush()

    result = merge_hosts(db_session, op.id, src.id, tgt.id)
    assert result["counts"]["connections_moved"] == 3

    # No record still references src.
    leftover = (
        db_session.query(ConnectionRecord)
        .filter((ConnectionRecord.src_host_id == src.id) |
                (ConnectionRecord.dst_host_id == src.id)).count()
    )
    assert leftover == 0

    # The src→tgt record is now a self-loop on tgt — preserved, not deleted.
    self_loops = (
        db_session.query(ConnectionRecord)
        .filter(ConnectionRecord.src_host_id == tgt.id,
                ConnectionRecord.dst_host_id == tgt.id).count()
    )
    assert self_loops == 1


# ─── Resolutions ─────────────────────────────────────────────────────────────

def test_resolution_pick_source_nickname(db_session):
    op = _op(db_session)
    src = _host(db_session, op.id, "src-nick")
    tgt = _host(db_session, op.id, "tgt-nick")
    merge_hosts(db_session, op.id, src.id, tgt.id, resolutions={"nickname": "source"})
    refreshed = db_session.query(Host).filter(Host.id == tgt.id).one()
    assert refreshed.nickname == "src-nick"


def test_resolution_pick_target_nickname_default(db_session):
    op = _op(db_session)
    src = _host(db_session, op.id, "src-nick")
    tgt = _host(db_session, op.id, "tgt-nick")
    merge_hosts(db_session, op.id, src.id, tgt.id, resolutions={"nickname": "target"})
    assert db_session.query(Host).filter(Host.id == tgt.id).one().nickname == "tgt-nick"


def test_resolution_freetext_nickname(db_session):
    op = _op(db_session)
    src = _host(db_session, op.id, "src-nick")
    tgt = _host(db_session, op.id, "tgt-nick")
    merge_hosts(db_session, op.id, src.id, tgt.id,
                resolutions={"nickname": "frankenhost"})
    assert db_session.query(Host).filter(Host.id == tgt.id).one().nickname == "frankenhost"


def test_resolution_pick_source_status(db_session):
    op = _op(db_session)
    src = _host(db_session, op.id, "s", status="compromised")
    tgt = _host(db_session, op.id, "t", status="pivot")
    merge_hosts(db_session, op.id, src.id, tgt.id, resolutions={"status": "source"})
    assert db_session.query(Host).filter(Host.id == tgt.id).one().status == "compromised"


def test_resolution_pick_source_comment(db_session):
    op = _op(db_session)
    src = _host(db_session, op.id, "s", comment="src comment")
    tgt = _host(db_session, op.id, "t", comment="tgt comment")
    merge_hosts(db_session, op.id, src.id, tgt.id, resolutions={"comment": "source"})
    assert db_session.query(Host).filter(Host.id == tgt.id).one().comment == "src comment"


def test_no_resolutions_keeps_target_values(db_session):
    op = _op(db_session)
    src = _host(db_session, op.id, "s", comment="src", status="pivot")
    tgt = _host(db_session, op.id, "t", comment="tgt", status="compromised")
    merge_hosts(db_session, op.id, src.id, tgt.id)
    refreshed = db_session.query(Host).filter(Host.id == tgt.id).one()
    assert refreshed.nickname == "t"
    assert refreshed.comment == "tgt"
    assert refreshed.status == "compromised"
