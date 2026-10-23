"""Tests for the voice webhook's server-side confirmation and identity gates."""

import json

from sqlalchemy import select

from app.data.models import Patient
from app.services.patients import PatientService
from app.telephony.webhook import _dispatch_tool, _handle_conversation_update, _handle_lookup


def _conversation(session, call_id: str, assistant_text: str, user_text: str) -> None:
    """Persist a minimal Vapi conversation update for a tool call."""

    _handle_conversation_update(
        {
            "call": {"id": call_id},
            "messages": [
                {"role": "assistant", "message": assistant_text},
                {"role": "user", "message": user_text},
            ],
        },
        session,
    )


def _save_tool_call(call_id: str, patient_payload: dict[str, object]) -> dict[str, str]:
    """Build a fake Vapi save call with a model-supplied confirmation flag."""

    return {
        "id": "tool-save-1",
        "function": {
            "name": "save_patient",
            "arguments": json.dumps(
                {"caller_confirmation": "yes", "patient": patient_payload}
            ),
        },
    }


def test_save_rejected_without_spoken_confirmation(db_session, patient_payload) -> None:
    """A model flag alone cannot authorize a patient write."""

    result = _dispatch_tool(
        _save_tool_call("call-no-confirm", patient_payload), db_session, "call-no-confirm"
    )

    assert json.loads(result["result"])["ok"] is False
    assert db_session.scalars(select(Patient)).all() == []


def test_save_rejected_when_last_user_turn_is_no(db_session, patient_payload) -> None:
    """A negative spoken answer blocks a write even if the model says yes."""

    call_id = "call-negative"
    _conversation(db_session, call_id, "Is all of that correct?", "No, the ZIP is wrong.")

    result = _dispatch_tool(_save_tool_call(call_id, patient_payload), db_session, call_id)

    assert json.loads(result["result"])["ok"] is False
    assert db_session.scalars(select(Patient)).all() == []


def test_save_requires_affirmative_after_confirmation_question(db_session, patient_payload) -> None:
    """A caller's yes must follow the assistant's full-readback question."""

    call_id = "call-affirmative"
    _conversation(db_session, call_id, "Is all of that correct?", "Yes, I confirm.")

    result = _dispatch_tool(_save_tool_call(call_id, patient_payload), db_session, call_id)

    assert json.loads(result["result"])["saved"] is True
    assert len(db_session.scalars(select(Patient)).all()) == 1


def test_update_requires_backend_verified_identity(db_session, patient_payload) -> None:
    """A model cannot update a patient unless this call verified phone and DOB."""

    patient = PatientService(db_session).create(patient_payload)
    call_id = "call-update-unverified"
    _conversation(db_session, call_id, "Is all of that correct?", "Yes.")
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
    _conversation(db_session, call_id, "Is all of that correct?", "Yes.")
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


def test_duplicate_save_returns_verified_update_branch_and_consumes_yes(
    db_session, patient_payload
) -> None:
    """A duplicate with matching DOB offers update, but cannot reuse save consent."""

    patient = PatientService(db_session).create(patient_payload)
    call_id = "call-duplicate-matching-dob"
    _conversation(db_session, call_id, "Is all of that correct?", "Yes.")

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

    assert json.loads(stale_update["result"])["ok"] is False
    assert patient.city == "Sample City"


def test_duplicate_save_does_not_disclose_when_dob_does_not_match(
    db_session, patient_payload
) -> None:
    """A phone match alone never returns another patient's details."""

    PatientService(db_session).create(patient_payload)
    call_id = "call-duplicate-wrong-dob"
    _conversation(db_session, call_id, "Is all of that correct?", "Yes.")
    wrong_dob_payload = {**patient_payload, "date_of_birth": "03/15/1990"}

    result = _dispatch_tool(
        _save_tool_call(call_id, wrong_dob_payload), db_session, call_id
    )
    duplicate = json.loads(result["result"])

    assert duplicate["duplicate"] is True
    assert duplicate["identity_verified"] is False
    assert "patient" not in duplicate


def test_duplicate_update_requires_fresh_readback_and_yes(db_session, patient_payload) -> None:
    """After a duplicate, a later confirmed change can be updated exactly once."""

    patient = PatientService(db_session).create(patient_payload)
    call_id = "call-duplicate-fresh-confirmation"
    _conversation(db_session, call_id, "Is all of that correct?", "Yes.")
    _dispatch_tool(_save_tool_call(call_id, patient_payload), db_session, call_id)
    _handle_conversation_update(
        {
            "call": {"id": call_id},
            "messages": [
                {"role": "assistant", "message": "Is all of that correct?"},
                {"role": "user", "message": "Yes."},
                {
                    "role": "assistant",
                    "message": "Would you like to update your existing record?",
                },
                {"role": "user", "message": "Yes, I want to change my city."},
                {
                    "role": "assistant",
                    "message": "I have Sampleville as your city. Is that right, and is the rest still correct?",
                },
                {"role": "user", "message": "Yes, that's right."},
            ],
        },
        db_session,
    )

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
