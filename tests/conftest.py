"""Shared test fixtures."""
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from database import Base, get_db
from main import app


@pytest.fixture(scope="function")
def db_engine():
    """Create an in-memory SQLite engine for each test.

    StaticPool ensures all connections share the same in-memory database,
    which is required for SQLite :memory: to work correctly with SQLAlchemy.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a DB session bound to the in-memory engine."""
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI test client with DB dependency overridden."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # raise_server_exceptions=True so test failures surface properly
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """Redirect settings.upload_path to a temp directory for upload listing tests."""
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setattr("config.settings.upload_path", str(d))
    return d
