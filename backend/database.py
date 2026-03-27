"""SQLAlchemy engine, session, and declarative base."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings


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
    """Dependency: yield a DB session, close on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
