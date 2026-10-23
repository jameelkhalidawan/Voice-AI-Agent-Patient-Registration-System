"""SQLAlchemy engine and session setup."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


def _create_engine():
    """Create an engine with SQLite-specific local development options."""

    url = get_settings().database_url
    # SQLAlchemy otherwise selects psycopg2 for the bare postgresql:// scheme.
    # This project installs Psycopg 3, so force its explicit dialect+driver name.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    options = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, connect_args=options)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and always close it after the request."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
