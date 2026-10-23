"""Create tables and insert two clearly fake development patients."""

from datetime import date

from sqlalchemy import select

from app.data.database import Base, SessionLocal, engine
from app.data.models import Patient, Sex


def seed() -> None:
    """Create the schema and idempotently add two fake patients."""

    Base.metadata.create_all(engine)
    samples = [
        {
            "first_name": "Alex",
            "last_name": "Sample",
            "date_of_birth": date(1988, 4, 12),
            "sex": Sex.OTHER,
            "phone_number": "2025550147",
            "address_line_1": "100 Example Street",
            "city": "Washington",
            "state": "DC",
            "zip_code": "20001",
        },
        {
            "first_name": "Jamie",
            "last_name": "Demo",
            "date_of_birth": date(1992, 9, 3),
            "sex": Sex.DECLINE_TO_ANSWER,
            "phone_number": "2025550168",
            "address_line_1": "200 Sample Avenue",
            "city": "Washington",
            "state": "DC",
            "zip_code": "20002",
        },
    ]
    with SessionLocal() as session:
        for sample in samples:
            exists = session.scalar(
                select(Patient.patient_id).where(Patient.phone_number == sample["phone_number"])
            )
            if exists is None:
                session.add(Patient(**sample))
        session.commit()


if __name__ == "__main__":
    seed()
