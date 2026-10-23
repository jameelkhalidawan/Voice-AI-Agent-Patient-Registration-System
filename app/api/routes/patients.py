"""Patient REST endpoints."""

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.schemas import patient_to_dict, success
from app.api.security import require_write_api_key
from app.data.database import get_db
from app.services.patients import PatientService
from app.services.validation import FieldValidationError

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("")
def list_patients(
    last_name: str | None = Query(default=None),
    date_of_birth: str | None = Query(default=None),
    phone_number: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List active patients, with optional exact last-name, DOB, and phone filters."""

    patients = PatientService(session).list(
        last_name=last_name,
        date_of_birth=date_of_birth,
        phone_number=phone_number,
    )
    return success([patient_to_dict(patient) for patient in patients])


@router.get("/{patient_id}")
def get_patient(patient_id: uuid.UUID, session: Session = Depends(get_db)) -> dict[str, Any]:
    """Get one active patient by UUID."""

    return success(patient_to_dict(PatientService(session).get(patient_id)))


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_write_api_key)])
def create_patient(
    payload: dict[str, Any] = Body(...),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Validate and create a patient; write access requires X-API-Key."""

    patient = PatientService(session).create(payload)
    return success(patient_to_dict(patient))


@router.put("/{patient_id}", dependencies=[Depends(require_write_api_key)])
def update_patient(
    patient_id: uuid.UUID,
    payload: dict[str, Any] = Body(...),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Apply a partial update to an active patient."""

    if not payload:
        raise FieldValidationError("body", "Provide at least one field to update.")
    patient = PatientService(session).update(patient_id, payload)
    return success(patient_to_dict(patient))


@router.delete("/{patient_id}", dependencies=[Depends(require_write_api_key)])
def delete_patient(
    patient_id: uuid.UUID,
    response: Response,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Soft-delete an active patient; the row remains in the database."""

    patient = PatientService(session).soft_delete(patient_id)
    response.status_code = status.HTTP_200_OK
    return success(patient_to_dict(patient))
