"""Activity log helper — call log_activity() inside a write endpoint before db.commit()."""
from typing import Optional

from sqlalchemy.orm import Session

from models import ActivityLog


def log_activity(
    db: Session,
    op_id: str,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    """Add an ActivityLog entry to the current session.

    The caller is responsible for committing — the log entry is part of the
    same transaction as the entity write, so a rollback removes both atomically.
    """
    entry = ActivityLog(
        op_id=op_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail,
    )
    db.add(entry)
