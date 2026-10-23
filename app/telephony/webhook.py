"""Authenticated Vapi tool and end-of-call webhook handlers."""

from __future__ import annotations

import hmac
import json
import logging
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.schemas import patient_to_dict
from app.config import get_settings
from app.data.database import get_db
from app.data.models import CallLog, Patient
from app.services.patients import (
    DuplicatePhoneError,
    PatientNotFoundError,
    PatientService,
)
from app.services.validation import (
    FIELD_LIMITS,
    FieldValidationError,
    normalize_dob,
    validate_patient_payload,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["vapi"])

_REQUIRED_PATIENT_FIELDS = {
    "first_name",
    "last_name",
    "date_of_birth",
    "sex",
    "phone_number",
    "address_line_1",
    "city",
    "state",
    "zip_code",
}
_VOICE_VALIDATABLE_FIELDS = sorted(
    _REQUIRED_PATIENT_FIELDS | set(FIELD_LIMITS) | {"emergency_contact_phone"}
)


def _matches_webhook_secret(authorization: str | None, legacy_secret: str | None) -> bool:
    """Compare accepted Vapi auth headers against the configured secret."""

    expected = get_settings().vapi_webhook_secret
    if not expected:
        return False
    candidates: list[str] = []
    if authorization:
        scheme, separator, token = authorization.partition(" ")
        if separator and scheme.casefold() == "bearer":
            candidates.append(token.strip())
    if legacy_secret:
        candidates.append(legacy_secret.strip())
    return any(hmac.compare_digest(candidate, expected) for candidate in candidates)


def _json_safe(value: Any) -> Any:
    """Convert normalized Python values to JSON-compatible primitives."""

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _tool_arguments(raw: Any) -> dict[str, Any]:
    """Parse an object or JSON-encoded object from Vapi's tool arguments."""

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("The tool arguments were not valid JSON.") from exc
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("The tool arguments must be a JSON object.")


def _call_id(message: dict[str, Any]) -> str | None:
    """Return the Vapi call ID when included in the event."""

    call = message.get("call")
    value = call.get("id") if isinstance(call, dict) else None
    return value if isinstance(value, str) and value else None


def _store_call_log(
    session: Session,
    *,
    call_id: str,
    status: str,
    patient: Patient | None = None,
    transcript: str | None = None,
    summary: str | None = None,
    final_payload: dict[str, Any] | None = None,
) -> None:
    """Create or update one call log without discarding earlier call data."""

    try:
        record = session.get(CallLog, call_id)
        if record is None:
            record = CallLog(call_id=call_id, status=status)
            session.add(record)
        if patient is not None:
            record.patient_id = patient.patient_id
        if transcript is not None:
            record.transcript = transcript
        if summary is not None:
            record.summary = summary
        if final_payload is not None:
            record.final_payload = _json_safe(final_payload)
        if status == "partial" and record.status in {"registered", "updated"}:
            # A completed registration remains successful even if the caller
            # hangs up before the post-call report is delivered.
            pass
        else:
            record.status = status
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.error("vapi_call_log_write_failed", extra={"call_id": call_id})


def _validation_error_result(tool_call_id: str, message: str) -> dict[str, str]:
    """Build a Vapi-specific tool error result (the error must be a string)."""

    return {"toolCallId": tool_call_id, "error": message}


def _tool_failure_result(
    tool_call_id: str, message: str, *, field: str | None = None
) -> dict[str, str]:
    """Return recoverable business failures as a string result for the model."""

    result: dict[str, Any] = {"ok": False, "message": message}
    if field:
        result["field"] = field
    return {
        "toolCallId": tool_call_id,
        "result": json.dumps(result, separators=(",", ":")),
    }


def _handle_lookup(
    args: dict[str, Any], session: Session, call_id: str | None
) -> dict[str, Any]:
    """Find an active patient and require DOB verification before disclosure."""

    phone_number = args.get("phone_number")
    patient = PatientService(session).find_by_phone(phone_number)
    if patient is None:
        _set_verified_patient(session, call_id, None)
        return {"found": False, "identity_verified": False}

    spoken_dob = args.get("date_of_birth")
    if spoken_dob is None:
        _set_verified_patient(session, call_id, None)
        return {
            "found": True,
            "identity_verified": False,
            "verify_date_of_birth": True,
        }
    normalized_dob = normalize_dob(spoken_dob)
    if normalized_dob != patient.date_of_birth:
        _set_verified_patient(session, call_id, None)
        return {
            "found": True,
            "identity_verified": False,
            "message": "The identifier did not match. Do not disclose record details; offer a clinic callback.",
        }
    _set_verified_patient(session, call_id, str(patient.patient_id))
    return {
        "found": True,
        "identity_verified": True,
        "patient": patient_to_dict(patient),
    }


def _handle_validate(args: dict[str, Any]) -> dict[str, Any]:
    """Run one field through the same server-side rules as the REST API."""

    field = args.get("field")
    if not isinstance(field, str) or field not in _VOICE_VALIDATABLE_FIELDS:
        raise FieldValidationError("field", "That field cannot be validated.")
    normalized = validate_patient_payload({field: args.get("value")}, partial=True)
    return {"valid": True, "field": field, "normalized_value": _json_safe(normalized[field])}


def _message_text(message: dict[str, Any]) -> str:
    """Extract readable text from a Vapi conversation message."""

    for key in ("message", "content", "text"):
        value = message.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = [
                item.get("text", "")
                for item in value
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ]
            if parts:
                return " ".join(parts)
    return ""


def _workflow_state(session: Session, call_id: str | None) -> dict[str, Any]:
    """Read live conversation evidence persisted in the call transcript field."""

    if not call_id:
        return {}
    record = session.get(CallLog, call_id)
    if record is None or not record.transcript:
        return {}
    try:
        stored = json.loads(record.transcript)
    except (TypeError, json.JSONDecodeError):
        return {}
    state = stored.get("_vapi_workflow") if isinstance(stored, dict) else None
    return state if isinstance(state, dict) else {}


def _save_workflow_state(
    session: Session, call_id: str | None, state: dict[str, Any]
) -> None:
    """Persist short-lived call evidence until the final report replaces it."""

    if not call_id:
        return
    record = session.get(CallLog, call_id)
    if record is None:
        record = CallLog(call_id=call_id, status="in_progress")
        session.add(record)
    record.transcript = json.dumps({"_vapi_workflow": state}, ensure_ascii=False)
    session.commit()


def _set_verified_patient(
    session: Session, call_id: str | None, patient_id: str | None
) -> None:
    """Record a patient identity only after the backend verifies the DOB."""

    if not call_id:
        return
    state = _workflow_state(session, call_id)
    state["verified_patient_id"] = patient_id
    try:
        _save_workflow_state(session, call_id, state)
    except SQLAlchemyError:
        session.rollback()
        logger.error("vapi_identity_state_write_failed", extra={"call_id": call_id})


def _is_clear_affirmative(text: str) -> bool:
    """Accept a clear affirmative, rejecting qualified or contradictory replies."""

    normalized = " ".join(text.casefold().strip().split())
    if any(word in normalized for word in (" but ", " except ", " not ", " however ")):
        return False
    return normalized.startswith(
        ("yes", "yeah", "yep", "correct", "that's right", "that is right", "i confirm", "go ahead")
    )


def _spoken_confirmation_index(state: dict[str, Any]) -> int | None:
    """Return the user-turn index for a fresh affirmative after a read-back."""

    messages = state.get("messages")
    if not isinstance(messages, list):
        return None
    local_user_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].get("role") == "user"),
        None,
    )
    if local_user_index is None:
        return None
    user_text = messages[local_user_index].get("text", "")
    if not isinstance(user_text, str) or not _is_clear_affirmative(user_text):
        return None
    assistant = next(
        (
            messages[index]
            for index in range(local_user_index - 1, -1, -1)
            if messages[index].get("role") == "assistant"
        ),
        None,
    )
    if not assistant:
        return None
    prompt = assistant.get("text", "").casefold()
    confirmed = any(
        phrase in prompt
        for phrase in (
            "is all of that correct",
            "is everything correct",
            "is that right",
            "is that correct",
            "is the rest still correct",
            "are those changes correct",
        )
    )
    absolute_index = messages[local_user_index].get("index", local_user_index)
    return absolute_index if confirmed and isinstance(absolute_index, int) else None


def _handle_conversation_update(message: dict[str, Any], session: Session) -> None:
    """Keep committed user and assistant turns for a server-side consent gate."""

    call_id = _call_id(message)
    raw_messages = message.get("messages")
    if not call_id or not isinstance(raw_messages, list):
        return
    messages: list[dict[str, Any]] = []
    base_index = max(0, len(raw_messages) - 100)
    for index, item in enumerate(raw_messages[base_index:], start=base_index):
        if not isinstance(item, dict) or item.get("role") not in {"assistant", "user"}:
            continue
        text = _message_text(item).strip()[:4000]
        if text:
            messages.append({"index": index, "role": item["role"], "text": text})
    state = _workflow_state(session, call_id)
    state["messages"] = messages
    try:
        _save_workflow_state(session, call_id, state)
    except SQLAlchemyError:
        session.rollback()
        logger.error("vapi_conversation_state_write_failed", extra={"call_id": call_id})


def _require_confirmation(
    args: dict[str, Any],
    session: Session,
    call_id: str | None,
    *,
    verified_patient_id: str | None = None,
) -> None:
    """Require both a model flag and verified Vapi conversation evidence."""

    if args.get("caller_confirmation") != "yes":
        raise FieldValidationError(
            "caller_confirmation",
            "Do not save or update until the caller explicitly confirms the complete read-back.",
        )
    state = _workflow_state(session, call_id)
    confirmation_index = _spoken_confirmation_index(state)
    if confirmation_index is None:
        raise FieldValidationError(
            "caller_confirmation",
            "The server has not received a clear caller yes after the complete read-back. Read it back, ask whether it is correct, and wait for the caller's answer before trying again.",
        )
    consumed_index = state.get("consumed_confirmation_index", -1)
    if not isinstance(consumed_index, int) or confirmation_index <= consumed_index:
        raise FieldValidationError(
            "caller_confirmation",
            "That confirmation was already used. Read back the current information or proposed changes, ask whether they are correct, and wait for a fresh yes.",
        )
    if verified_patient_id is not None and state.get("verified_patient_id") != verified_patient_id:
        raise FieldValidationError(
            "patient_id",
            "The existing record was not verified by the server during this call. Do not update it; offer a clinic callback.",
        )
    state["consumed_confirmation_index"] = confirmation_index
    _save_workflow_state(session, call_id, state)


def _handle_save(
    args: dict[str, Any], session: Session, call_id: str | None
) -> dict[str, Any]:
    """Validate, persist, and record a caller-confirmed new patient."""

    _require_confirmation(args, session, call_id)
    raw_patient = args.get("patient")
    if not isinstance(raw_patient, dict):
        raise FieldValidationError("patient", "The patient details were missing; please collect them again.")
    # PatientService owns normalization so this path uses exactly the same
    # validation behavior as the REST API.
    patient = PatientService(session).create(raw_patient)
    normalized = {field: getattr(patient, field) for field in raw_patient}
    if call_id:
        _store_call_log(
            session,
            call_id=call_id,
            status="registered",
            patient=patient,
            final_payload=normalized,
        )
    logger.info(
        "vapi_patient_registration_confirmed",
        extra={"call_id": call_id or "", "final_payload": _json_safe(normalized)},
    )
    return {"saved": True, "patient_id": str(patient.patient_id)}


def _handle_update(
    args: dict[str, Any], session: Session, call_id: str | None
) -> dict[str, Any]:
    """Apply only validated changed fields after caller confirmation."""

    patient_id = args.get("patient_id")
    changes = args.get("changes")
    if not isinstance(patient_id, str):
        raise FieldValidationError("patient_id", "The existing patient record could not be identified.")
    try:
        parsed_id = UUID(patient_id)
    except ValueError as exc:
        raise FieldValidationError("patient_id", "The existing patient record could not be identified.") from exc
    _require_confirmation(
        args, session, call_id, verified_patient_id=str(parsed_id)
    )
    if not isinstance(changes, dict) or not changes:
        raise FieldValidationError("changes", "Provide at least one confirmed change.")
    patient = PatientService(session).update(parsed_id, changes)
    normalized = {field: getattr(patient, field) for field in changes}
    if call_id:
        _store_call_log(
            session,
            call_id=call_id,
            status="updated",
            patient=patient,
            final_payload=normalized,
        )
    logger.info(
        "vapi_patient_update_confirmed",
        extra={"call_id": call_id or "", "final_payload": _json_safe(normalized)},
    )
    return {"updated": True, "patient_id": str(patient.patient_id)}


def _dispatch_tool(
    tool_call: dict[str, Any], session: Session, call_id: str | None
) -> dict[str, str]:
    """Execute one known Vapi function and return its matching result object."""

    tool_call_id = tool_call.get("id")
    if not isinstance(tool_call_id, str) or not tool_call_id:
        return _validation_error_result("missing-tool-call-id", "The tool call could not be correlated.")
    function = tool_call.get("function")
    if not isinstance(function, dict) or not isinstance(function.get("name"), str):
        return _validation_error_result(tool_call_id, "The tool call format was not recognized.")
    name = function["name"]
    try:
        args = _tool_arguments(function.get("arguments"))
        if name == "lookup_patient_by_phone":
            result = _handle_lookup(args, session, call_id)
        elif name == "validate_field":
            result = _handle_validate(args)
        elif name == "save_patient":
            result = _handle_save(args, session, call_id)
        elif name == "update_patient":
            result = _handle_update(args, session, call_id)
        else:
            return _validation_error_result(tool_call_id, "That tool is not available.")
        return {"toolCallId": tool_call_id, "result": json.dumps(_json_safe(result), separators=(",", ":"))}
    except FieldValidationError as exc:
        return _tool_failure_result(tool_call_id, exc.message, field=exc.field)
    except DuplicatePhoneError:
        if name == "save_patient":
            # A model may skip the earlier lookup tool. Recover the returning-
            # caller path here, but reveal details only after server-side DOB match.
            candidate = args.get("patient")
            if isinstance(candidate, dict):
                try:
                    existing = PatientService(session).find_by_phone(
                        candidate.get("phone_number")
                    )
                    submitted_dob = normalize_dob(candidate.get("date_of_birth"))
                except FieldValidationError:
                    existing = None
                    submitted_dob = None
                except SQLAlchemyError:
                    session.rollback()
                    logger.error(
                        "vapi_duplicate_lookup_failed",
                        extra={"call_id": call_id or ""},
                    )
                    return _tool_failure_result(
                        tool_call_id,
                        "A record may already use that phone number, but I could not verify it right now. Do not retry the registration; offer a clinic callback.",
                    )
                if existing is not None and submitted_dob == existing.date_of_birth:
                    _set_verified_patient(session, call_id, str(existing.patient_id))
                    result = {
                        "ok": False,
                        "duplicate": True,
                        "identity_verified": True,
                        "patient": patient_to_dict(existing),
                        "message": (
                            "A record matches the caller's phone number and date of birth. "
                            "Do not try to create it again. Tell the caller an existing record "
                            "was found and ask whether they want to update it. If they decline, "
                            "end politely. If they agree, apply only requested changes, read "
                            "back those changes, and wait for a fresh confirmation before update."
                        ),
                    }
                    return {
                        "toolCallId": tool_call_id,
                        "result": json.dumps(_json_safe(result), separators=(",", ":")),
                    }
                result = {
                    "ok": False,
                    "duplicate": True,
                    "identity_verified": False,
                    "message": (
                        "An active record uses that phone number, but the date of birth did not "
                        "verify it. Do not disclose any stored details or update it. Offer a clinic callback."
                    ),
                }
                return {
                    "toolCallId": tool_call_id,
                    "result": json.dumps(result, separators=(",", ":")),
                }
        return _tool_failure_result(
            tool_call_id,
            "An active record already uses that phone number. Do not claim the registration succeeded; offer the caller a callback.",
        )
    except PatientNotFoundError:
        return _tool_failure_result(
            tool_call_id,
            "The verified patient record was not found. Do not claim the update succeeded; offer a callback.",
        )
    except SQLAlchemyError:
        session.rollback()
        logger.error("vapi_patient_database_operation_failed", extra={"call_id": call_id or ""})
        return _tool_failure_result(
            tool_call_id,
            "I could not save that information right now. Please tell the caller honestly and offer one retry or a clinic callback.",
        )
    except Exception as exc:  # Defensive boundary: never leak internals to a caller.
        session.rollback()
        logger.error(
            "vapi_tool_operation_failed",
            extra={"call_id": call_id or "", "error_type": type(exc).__name__},
        )
        return _tool_failure_result(
            tool_call_id,
            "I could not complete that request. Please tell the caller honestly and offer a clinic callback.",
        )


def _handle_end_of_call(message: dict[str, Any], session: Session) -> None:
    """Persist the final transcript/summary and mark incomplete calls partial."""

    call_id = _call_id(message)
    if not call_id:
        logger.warning("vapi_end_of_call_without_call_id")
        return
    artifact = message.get("artifact") if isinstance(message.get("artifact"), dict) else {}
    transcript = artifact.get("transcript") or message.get("transcript")
    summary = message.get("summary")
    analysis = message.get("analysis")
    if not summary and isinstance(analysis, dict):
        summary = analysis.get("summary")
    if summary is not None and not isinstance(summary, str):
        summary = json.dumps(summary, ensure_ascii=False)
    try:
        record = session.get(CallLog, call_id)
        status = record.status if record and record.status in {"registered", "updated"} else "partial"
        _store_call_log(
            session,
            call_id=call_id,
            status=status,
            transcript=transcript if isinstance(transcript, str) else None,
            summary=summary,
        )
        logger.info(
            "vapi_end_of_call_report_saved",
            extra={"call_id": call_id, "call_status": status},
        )
    except SQLAlchemyError:
        session.rollback()
        logger.error("vapi_end_of_call_log_read_failed", extra={"call_id": call_id})


@router.post("/webhook/vapi", include_in_schema=False)
def receive_vapi_webhook(
    payload: dict[str, Any] = Body(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_vapi_secret: str | None = Header(default=None, alias="X-Vapi-Secret"),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Authenticate Vapi requests and dispatch tools or post-call reports."""

    settings = get_settings()
    if not settings.vapi_webhook_secret:
        raise HTTPException(status_code=503, detail="Vapi webhook authentication is not configured.")
    if not _matches_webhook_secret(authorization, x_vapi_secret):
        logger.warning("vapi_webhook_authentication_failed")
        raise HTTPException(status_code=401, detail="Invalid webhook credentials.")

    message = payload.get("message")
    if not isinstance(message, dict):
        raise HTTPException(status_code=400, detail="The Vapi message object is missing.")
    message_type = message.get("type")
    call_id = _call_id(message)
    if message_type == "tool-calls":
        tool_calls = message.get("toolCallList")
        if not isinstance(tool_calls, list):
            raise HTTPException(status_code=400, detail="The Vapi tool call list is missing.")
        results = [_dispatch_tool(item, session, call_id) for item in tool_calls if isinstance(item, dict)]
        if len(results) != len(tool_calls):
            results.extend(
                _validation_error_result("malformed-tool-call", "The tool call format was not recognized.")
                for item in tool_calls
                if not isinstance(item, dict)
            )
        return {"results": results}
    if message_type == "end-of-call-report":
        _handle_end_of_call(message, session)
        return {"received": True}
    if message_type in {"conversation-update", "transcript"}:
        if message_type == "conversation-update":
            _handle_conversation_update(message, session)
        # Transcript-only messages do not contain both sides of the confirmation
        # exchange, so they are intentionally insufficient to authorize a write.
        return {"received": True}
    logger.info(
        "vapi_event_received",
        extra={"call_id": call_id or "", "event_type": str(message_type or "unknown")},
    )
    return {"received": True}
