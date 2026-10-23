"""SQLAlchemy models for patients and optional call transcripts."""

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.data.database import Base


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


class Sex(str, enum.Enum):
    """Allowed patient sex selections from the intake form."""

    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE_TO_ANSWER = "Decline to Answer"


class Patient(Base):
    """Patient demographics and registration details."""

    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint("length(first_name) BETWEEN 1 AND 50", name="ck_patient_first_name_length"),
        CheckConstraint("length(last_name) BETWEEN 1 AND 50", name="ck_patient_last_name_length"),
        CheckConstraint("length(city) BETWEEN 1 AND 100", name="ck_patient_city_length"),
        CheckConstraint("length(state) = 2", name="ck_patient_state_length"),
        CheckConstraint("length(phone_number) = 10", name="ck_patient_phone_length"),
        CheckConstraint("length(zip_code) IN (5, 10)", name="ck_patient_zip_length"),
        Index(
            "uq_patients_active_phone_number",
            "phone_number",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[Sex] = mapped_column(SqlEnum(Sex, name="patient_sex", native_enum=False), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(10), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    address_line_1: Mapped[str] = mapped_column(String(200), nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)
    insurance_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    insurance_member_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(50), nullable=False, default="English", server_default="English")
    emergency_contact_name: Mapped[str | None] = mapped_column(String(101), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    call_logs: Mapped[list["CallLog"]] = relationship(
        back_populates="patient",
        primaryjoin="Patient.patient_id == CallLog.patient_id",
        foreign_keys="CallLog.patient_id",
    )


class CallLog(Base):
    """Optional end-of-call transcript and summary record."""

    __tablename__ = "call_logs"

    call_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.patient_id"), nullable=True, index=True
    )
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now())
    patient: Mapped[Patient | None] = relationship(back_populates="call_logs", foreign_keys=[patient_id])
