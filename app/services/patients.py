"""Patient persistence operations shared by API routes and voice tools."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data.models import Patient
from app.services.validation import FieldValidationError, normalize_phone, validate_patient_payload


class DuplicatePhoneError(ValueError):
    """Raised when an active patient already owns a normalized phone number."""


class PatientNotFoundError(LookupError):
    """Raised when a patient is missing or soft-deleted."""


def _is_active_phone_unique_violation(error: IntegrityError) -> bool:
    """Identify only the active-phone partial unique-index violation."""

    original = error.orig
    diag = getattr(original, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name == "uq_patients_active_phone_number":
        return True
    # SQLite reports columns rather than the partial index's name.
    message = str(original)
    return "UNIQUE constraint failed: patients.phone_number" in message


class PatientService:
    """CRUD operations that always exclude soft-deleted patients by default."""

    def __init__(self, session: Session):
        """Bind service operations to one request-scoped SQLAlchemy session."""

        self.session = session

    def create(self, payload: dict[str, Any]) -> Patient:
        """Validate and persist a new active patient."""

        normalized = validate_patient_payload(payload)
        patient = Patient(**normalized)
        self.session.add(patient)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            if _is_active_phone_unique_violation(exc):
                raise DuplicatePhoneError("An active patient already has that phone number.") from exc
            raise
        self.session.refresh(patient)
        return patient

    def get(self, patient_id: uuid.UUID) -> Patient:
        """Get an active patient or raise PatientNotFoundError."""

        patient = self.session.scalar(
            select(Patient).where(Patient.patient_id == patient_id, Patient.deleted_at.is_(None))
        )
        if patient is None:
            raise PatientNotFoundError("Patient not found.")
        return patient

    def list(
        self,
        *,
        last_name: str | None = None,
        date_of_birth: Any | None = None,
        phone_number: str | None = None,
    ) -> list[Patient]:
        """List active patients with optional normalized filters."""

        query = select(Patient).where(Patient.deleted_at.is_(None))
        if last_name:
            # Exact, case-insensitive matching; caller input is not treated as LIKE syntax.
            query = query.where(func.lower(Patient.last_name) == last_name.strip().lower())
        if date_of_birth is not None:
            from app.services.validation import normalize_dob

            query = query.where(Patient.date_of_birth == normalize_dob(date_of_birth))
        if phone_number:
            normalized_phone = normalize_phone("phone_number", phone_number)
            query = query.where(Patient.phone_number == normalized_phone)
        return list(self.session.scalars(query.order_by(Patient.created_at.desc())).all())

    def update(self, patient_id: uuid.UUID, changes: dict[str, Any]) -> Patient:
        """Validate and apply only supplied fields to an active patient."""

        patient = self.get(patient_id)
        normalized = validate_patient_payload(changes, partial=True)
        if "phone_number" in normalized:
            other = self.find_by_phone(normalized["phone_number"])
            if other is not None and other.patient_id != patient.patient_id:
                raise DuplicatePhoneError("An active patient already has that phone number.")
        for field, value in normalized.items():
            setattr(patient, field, value)
        patient.updated_at = datetime.now(timezone.utc)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            if _is_active_phone_unique_violation(exc):
                raise DuplicatePhoneError("An active patient already has that phone number.") from exc
            raise
        self.session.refresh(patient)
        return patient

    def soft_delete(self, patient_id: uuid.UUID) -> Patient:
        """Mark an active patient deleted without removing its row."""

        patient = self.get(patient_id)
        patient.deleted_at = datetime.now(timezone.utc)
        patient.updated_at = patient.deleted_at
        self.session.commit()
        self.session.refresh(patient)
        return patient

    def find_by_phone(self, phone_number: str) -> Patient | None:
        """Find an active patient by a formatted or normalized US phone number."""

        normalized_phone = normalize_phone("phone_number", phone_number)
        return self.session.scalar(
            select(Patient).where(
                Patient.phone_number == normalized_phone,
                Patient.deleted_at.is_(None),
            )
        )
