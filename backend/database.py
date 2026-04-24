"""SQLAlchemy engine, session, and declarative base."""
import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator

from config import settings


class TZDateTime(TypeDecorator):
    """Stores datetimes as UTC; attaches UTC tzinfo on read so JS sees a Z suffix."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, datetime) and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return value.replace(tzinfo=timezone.utc)
        return value


def get_db_url() -> str:
    db_path = settings.db_path
    # Ensure the parent directory exists
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    return f"sqlite:///{db_path}"


engine = create_engine(
    get_db_url(),
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency: yield a DB session, roll back on unhandled exception, close on exit."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
