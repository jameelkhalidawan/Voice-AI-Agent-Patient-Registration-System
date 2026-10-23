"""Tests for explicit tool confirmation and backend identity verification."""

import json

from sqlalchemy import select

from app.data.models import Patient
from app.services.patients import PatientService
from app.telephony.webhook import _dispatch_tool, _handle_lookup


def _save_tool_call(
    call_id: str,
    patient_payload: dict[str, object],
    *,
    confirmation: str | None = "yes",
) -> dict[str, str]:
    """Build a fake Vapi save call with an optional confirmation flag."""

    arguments: dict[str, object] = {"patient": patient_payload}
    if confirmation is not None:
        arguments["caller_confirmation"] = confirmation

    return {
        "id": "tool-save-1",
        "function": {
            "name": "save_patient",
            "arguments": json.dumps(arguments),
        },
    }


def test_save_rejected_without_confirmation_flag(db_session, patient_payload) -> None:
    """A save call without an explicit confirmation flag cannot write."""

    result = _dispatch_tool(
        _save_tool_call("call-no-confirm", patient_payload, confirmation=None),
        db_session,
        "call-no-confirm",
    )

    assert json.loads(result["result"])["ok"] is False
    assert db_session.scalars(select(Patient)).all() == []


def test_save_rejected_when_confirmation_flag_is_no(db_session, patient_payload) -> None:
    """A negative confirmation flag blocks a write."""

    call_id = "call-negative"
    result = _dispatch_tool(
        _save_tool_call(call_id, patient_payload, confirmation="no"),
        db_session,
        call_id,
    )

    assert json.loads(result["result"])["ok"] is False
    assert db_session.scalars(select(Patient)).all() == []


def test_save_allowed_with_confirmation_flag_without_conversation_update(
    db_session, patient_payload
) -> None:
    """The confirmation flag allows saving if a conversation event is delayed or absent."""

    call_id = "call-affirmative"
    result = _dispatch_tool(_save_tool_call(call_id, patient_payload), db_session, call_id)

    assert json.loads(result["result"])["saved"] is True
    assert len(db_session.scalars(select(Patient)).all()) == 1


def test_update_requires_backend_verified_identity(db_session, patient_payload) -> None:
    """A model cannot update a patient unless this call verified phone and DOB."""

    patient = PatientService(db_session).create(patient_payload)
    call_id = "call-update-unverified"
    result = _dispatch_tool(
        {
            "id": "tool-update-1",
            "function": {
                "name": "update_patient",
                "arguments": json.dumps(
                    {
                        "caller_confirmation": "yes",
                        "patient_id": str(patient.patient_id),
                        "changes": {"email": "changed@example.test"},
                    }
                ),
            },
        },
        db_session,
        call_id,
    )

    assert json.loads(result["result"])["ok"] is False
    assert patient.email is None


def test_update_allowed_after_backend_dob_verification(db_session, patient_payload) -> None:
    """The verified patient ID is persisted by the lookup handler for later gating."""

    patient = PatientService(db_session).create(patient_payload)
    call_id = "call-update-verified"
    lookup = _handle_lookup(
        {
            "phone_number": patient.phone_number,
            "date_of_birth": patient.date_of_birth.isoformat(),
        },
        db_session,
        call_id,
    )
    assert lookup["identity_verified"] is True

    result = _dispatch_tool(
        {
            "id": "tool-update-2",
            "function": {
                "name": "update_patient",
                "arguments": json.dumps(
                    {
                        "caller_confirmation": "yes",
                        "patient_id": str(patient.patient_id),
                        "changes": {"email": "changed@example.test"},
                    }
                ),
            },
        },
        db_session,
        call_id,
    )

    assert json.loads(result["result"])["updated"] is True
    assert patient.email == "changed@example.test"


def test_duplicate_save_returns_verified_update_branch_and_requires_update_confirmation(
    db_session, patient_payload
) -> None:
    """A matching duplicate verifies identity but an update still needs its own yes flag."""

    patient = PatientService(db_session).create(patient_payload)
    call_id = "call-duplicate-matching-dob"
    duplicate_result = _dispatch_tool(
        _save_tool_call(call_id, patient_payload), db_session, call_id
    )
    duplicate = json.loads(duplicate_result["result"])

    assert duplicate["duplicate"] is True
    assert duplicate["identity_verified"] is True
    assert duplicate["patient"]["patient_id"] == str(patient.patient_id)
    assert len(db_session.scalars(select(Patient)).all()) == 1

    stale_update = _dispatch_tool(
        {
            "id": "tool-update-stale-confirmation",
            "function": {
                "name": "update_patient",
                "arguments": json.dumps(
                    {
                        "patient_id": str(patient.patient_id),
                        "changes": {"city": "Sampleville"},
                    }
                ),
            },
        },
        db_session,
        call_id,
    )

    assert json.loads(stale_update["result"])["ok"] is False
    assert patient.city == "Sample City"


def test_duplicate_save_does_not_disclose_when_dob_does_not_match(
    db_session, patient_payload
) -> None:
    """A phone match alone never returns another patient's details."""

    PatientService(db_session).create(patient_payload)
    call_id = "call-duplicate-wrong-dob"
    wrong_dob_payload = {**patient_payload, "date_of_birth": "03/15/1990"}

    result = _dispatch_tool(
        _save_tool_call(call_id, wrong_dob_payload), db_session, call_id
    )
    duplicate = json.loads(result["result"])

    assert duplicate["duplicate"] is True
    assert duplicate["identity_verified"] is False
    assert "patient" not in duplicate


def test_duplicate_update_allowed_with_verified_identity_and_confirmation_flag(
    db_session, patient_payload
) -> None:
    """A duplicate's verified identity permits a later explicitly confirmed update."""

    patient = PatientService(db_session).create(patient_payload)
    call_id = "call-duplicate-fresh-confirmation"
    _dispatch_tool(_save_tool_call(call_id, patient_payload), db_session, call_id)

    result = _dispatch_tool(
        {
            "id": "tool-update-fresh-confirmation",
            "function": {
                "name": "update_patient",
                "arguments": json.dumps(
                    {
                        "caller_confirmation": "yes",
                        "patient_id": str(patient.patient_id),
                        "changes": {"city": "Sampleville"},
                    }
                ),
            },
        },
        db_session,
        call_id,
    )

    assert json.loads(result["result"])["updated"] is True
    assert patient.city == "Sampleville"
