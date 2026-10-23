"""Response helpers and patient serialization for the REST API."""

from datetime import date, datetime
from typing import Any

from app.data.models import Patient


def success(data: Any) -> dict[str, Any]:
    """Wrap a successful response in the consistent API envelope."""

    return {"data": data, "error": None}


def patient_to_dict(patient: Patient) -> dict[str, Any]:
    """Serialize a patient model without exposing ORM internals."""

    result: dict[str, Any] = {}
    for field in (
        "patient_id", "first_name", "last_name", "date_of_birth", "sex",
        "phone_number", "email", "address_line_1", "address_line_2", "city",
        "state", "zip_code", "insurance_provider", "insurance_member_id",
        "preferred_language", "emergency_contact_name", "emergency_contact_phone",
        "created_at", "updated_at", "deleted_at",
    ):
        value = getattr(patient, field)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        elif hasattr(value, "value"):
            value = value.value
        elif field == "patient_id":
            value = str(value)
        result[field] = value
    return result
