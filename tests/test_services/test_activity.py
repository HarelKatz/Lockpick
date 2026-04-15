"""Unit tests for services/activity.py — log_activity()."""
import pytest
from sqlalchemy.orm import Session

from models import ActivityLog, Operation
from services.activity import log_activity


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_op(db: Session, name: str = "Test Op") -> Operation:
    op = Operation(name=name)
    db.add(op)
    db.flush()
    return op


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_entry_added_to_session(db_session):
    op = _make_op(db_session)
    log_activity(db_session, op.id, "create", "host")
    db_session.flush()
    count = db_session.query(ActivityLog).count()
    assert count == 1


def test_all_fields_stored(db_session):
    op = _make_op(db_session)
    log_activity(
        db_session,
        op.id,
        action="delete",
        entity_type="credential",
        entity_id="abc-123",
        detail="removed key for root",
    )
    db_session.flush()
    entry = db_session.query(ActivityLog).one()
    assert entry.op_id == op.id
    assert entry.action == "delete"
    assert entry.entity_type == "credential"
    assert entry.entity_id == "abc-123"
    assert entry.detail == "removed key for root"


def test_minimal_call_stores_none_optionals(db_session):
    op = _make_op(db_session)
    log_activity(db_session, op.id, "create", "operation")
    db_session.flush()
    entry = db_session.query(ActivityLog).one()
    assert entry.entity_id is None
    assert entry.detail is None


def test_rollback_removes_entry(db_session):
    op = _make_op(db_session)
    # Commit op so it persists; then verify the log entry is rolled back separately.
    db_session.commit()

    log_activity(db_session, op.id, "create", "host")
    db_session.flush()
    assert db_session.query(ActivityLog).count() == 1
    db_session.rollback()
    assert db_session.query(ActivityLog).count() == 0


def test_multiple_entries_in_one_session(db_session):
    op = _make_op(db_session)
    log_activity(db_session, op.id, "create", "host", entity_id="h1")
    log_activity(db_session, op.id, "create", "host", entity_id="h2")
    log_activity(db_session, op.id, "delete", "credential", entity_id="c1")
    db_session.flush()
    entries = db_session.query(ActivityLog).all()
    assert len(entries) == 3
    ids = {e.entity_id for e in entries}
    assert ids == {"h1", "h2", "c1"}
