"""Create the SQLAlchemy schema in the configured database."""

from app.data.database import Base, engine
from app.data import models  # noqa: F401 - registers mapped classes with Base metadata


def create_schema() -> None:
    """Create tables and indexes that do not already exist."""

    Base.metadata.create_all(engine)


if __name__ == "__main__":
    create_schema()
