"""Fixtures using an isolated temporary SQLite database, never the hosted DB."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient

from app.config import get_settings
from app.data.database import get_db
from app.main import app
from app.data.database import Base
from app.data import models  # noqa: F401 - register mapped models


@pytest.fixture
def db_session(tmp_path) -> Iterator[Session]:
    """Create a fresh file-backed database for each test."""

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False, "timeout": 20},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def patient_payload() -> dict[str, object]:
    """Return clearly fake valid patient details for persistence tests."""

    return {
        "first_name": "Taylor",
        "last_name": "McDonald",
        "date_of_birth": "03/14/1990",
        "sex": "Other",
        "phone_number": "2025550198",
        "address_line_1": "1 Example Way",
        "city": "Sample City",
        "state": "Texas",
        "zip_code": "75001",
    }


@pytest.fixture
def api_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    """Provide a TestClient backed by a disposable database and test-only key."""

    monkeypatch.setenv("API_KEY", "stage5-test-api-key")
    monkeypatch.delenv("RATE_LIMIT_PER_MINUTE", raising=False)
    get_settings.cache_clear()
    # Rebuild middleware per test so the in-memory rate-limit window is isolated.
    app.middleware_stack = None
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api-test.db'}",
        connect_args={"check_same_thread": False, "timeout": 20},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()
