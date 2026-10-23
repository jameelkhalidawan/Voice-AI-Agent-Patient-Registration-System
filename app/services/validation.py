"""Shared, server-side patient field normalization and validation."""

import re
import unicodedata
from datetime import date, datetime
from typing import Any

from app.data.models import Sex

MAX_AGE_YEARS = 120
FIELD_LIMITS = {
    "email": 254,
    "address_line_1": 200,
    "address_line_2": 200,
    "city": 100,
    "state": 100,
    "zip_code": 10,
    "insurance_provider": 100,
    "insurance_member_id": 100,
    "preferred_language": 50,
    "emergency_contact_name": 101,
}
STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}
VALID_STATE_CODES = frozenset(STATE_CODES.values())
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '-][^\W\d_]+)*$", re.UNICODE)
EMAIL_RE = re.compile(r"^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$")
ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")


class FieldValidationError(ValueError):
    """Validation failure with a stable field name and speakable message."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


def sanitize_string(field: str, value: Any, *, required: bool = False) -> str | None:
    """Strip controls and surrounding whitespace, rejecting empty/overlong text."""

    if value is None:
        if required:
            raise FieldValidationError(field, f"Please provide {field.replace('_', ' ')}.")
        return None
    if not isinstance(value, str):
        raise FieldValidationError(field, f"Please provide {field.replace('_', ' ')} as text.")
    cleaned = "".join(ch for ch in value if unicodedata.category(ch) != "Cc").strip()
    if not cleaned:
        if required:
            raise FieldValidationError(field, f"Please provide {field.replace('_', ' ')}.")
        return None
    if "<" in cleaned or ">" in cleaned:
        raise FieldValidationError(field, f"Please remove markup from {field.replace('_', ' ')}.")
    limit = FIELD_LIMITS.get(field, 200)
    if len(cleaned) > limit:
        raise FieldValidationError(field, f"That {field.replace('_', ' ')} is too long (maximum {limit} characters).")
    return cleaned


def normalize_name(field: str, value: Any, *, required: bool = True) -> str | None:
    """Validate a person name, preserving caller-provided capitalization."""

    name = sanitize_string(field, value, required=required)
    if name is None:
        return None
    name = re.sub(r"\s+", " ", name)
    if len(name) > 50:
        raise FieldValidationError(field, "That name is too long; please use 50 characters or fewer.")
    if not NAME_RE.fullmatch(name) or not any(char.isalpha() for char in name):
        raise FieldValidationError(field, "Use letters, spaces, hyphens, or apostrophes for the name.")
    # Preserve casing because names such as McDonald and O'Brien have meaningful
    # capitalization conventions that cannot be inferred reliably.
    return name


def normalize_dob(value: Any, *, today: date | None = None) -> date:
    """Parse common numeric, ISO, and spoken-month DOB forms and validate age."""

    current = today or date.today()
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        raw = sanitize_string("date_of_birth", value, required=True)
        assert raw is not None
        parsed = None
        for pattern in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
            try:
                parsed = datetime.strptime(raw, pattern).date()
                break
            except ValueError:
                continue
        if parsed is None:
            raise FieldValidationError("date_of_birth", "Please say the date of birth as month, day, and year.")
    else:
        raise FieldValidationError("date_of_birth", "Please say the date of birth as month, day, and year.")
    if parsed > current:
        raise FieldValidationError("date_of_birth", "The date of birth can’t be in the future.")
    try:
        oldest_date = current.replace(year=current.year - MAX_AGE_YEARS)
    except ValueError:
        # A Feb 29 reference date maps to Feb 28 in a non-leap cutoff year.
        oldest_date = current.replace(year=current.year - MAX_AGE_YEARS, day=28)
    if parsed < oldest_date:
        raise FieldValidationError("date_of_birth", "Please check that date; it would make the patient older than 120.")
    return parsed


def normalize_sex(value: Any) -> Sex:
    """Return the supported sex enumeration, ignoring letter case."""

    text = sanitize_string("sex", value, required=True)
    assert text is not None
    for option in Sex:
        if text.casefold() == option.value.casefold():
            return option
    raise FieldValidationError("sex", "Choose Male, Female, Other, or Decline to Answer.")


def normalize_phone(field: str, value: Any, *, required: bool = True) -> str | None:
    """Normalize US phone digits, optionally accepting a leading country code."""

    text = sanitize_string(field, value, required=required)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        count = len(digits)
        detail = f"only {count} digits" if count < 10 else f"{count} digits"
        raise FieldValidationError(field, f"That phone number looks like it has {detail}; please give a 10-digit US number.")
    if digits[0] in "01" or digits[3] in "01":
        raise FieldValidationError(field, "That phone number has an invalid US area or exchange code.")
    return digits


def normalize_email(value: Any, *, required: bool = False) -> str | None:
    """Validate and lowercase an optional email address."""

    email = sanitize_string("email", value, required=required)
    if email is None:
        return None
    if not EMAIL_RE.fullmatch(email):
        raise FieldValidationError("email", "That email address doesn’t look complete; please say it again.")
    return email.lower()


def normalize_state(value: Any) -> str:
    """Convert a US state name or code to its two-letter abbreviation."""

    state = sanitize_string("state", value, required=True)
    assert state is not None
    key = state.casefold()
    if key in STATE_CODES:
        return STATE_CODES[key]
    code = state.upper()
    if code in VALID_STATE_CODES:
        return code
    raise FieldValidationError("state", "Please give a valid US state or DC.")


def normalize_zip(value: Any) -> str:
    """Validate a five-digit or ZIP+4 postal code."""

    zip_code = sanitize_string("zip_code", value, required=True)
    assert zip_code is not None
    compact = zip_code.replace(" ", "")
    if compact.isdigit() and len(compact) == 9:
        compact = f"{compact[:5]}-{compact[5:]}"
    if not ZIP_RE.fullmatch(compact):
        raise FieldValidationError("zip_code", "Please give a 5-digit ZIP code or ZIP+4.")
    return compact


def normalize_member_id(value: Any, *, required: bool = False) -> str | None:
    """Validate an optional alphanumeric insurance member identifier."""

    member_id = sanitize_string("insurance_member_id", value, required=required)
    if member_id is None:
        return None
    if not member_id.isalnum():
        raise FieldValidationError("insurance_member_id", "The insurance member ID should contain only letters and numbers.")
    return member_id


def validate_patient_payload(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    """Normalize and validate patient fields for API and voice-tool use.

    Partial updates reject blank values for required fields. Blank/null optional
    values clear nullable fields to None. An empty preferred_language resets
    that non-nullable field to its model default, English.
    """

    result: dict[str, Any] = {}
    normalizers = {
        "first_name": normalize_name,
        "last_name": normalize_name,
        "date_of_birth": lambda value, **_: normalize_dob(value),
        "sex": lambda value, **_: normalize_sex(value),
        "phone_number": lambda value, **_: normalize_phone("phone_number", value),
        "emergency_contact_phone": lambda value, **_: normalize_phone("emergency_contact_phone", value, required=False),
        "email": normalize_email,
        "state": lambda value, **_: normalize_state(value),
        "zip_code": lambda value, **_: normalize_zip(value),
        "insurance_member_id": normalize_member_id,
    }
    required = {"first_name", "last_name", "date_of_birth", "sex", "phone_number", "address_line_1", "city", "state", "zip_code"}
    allowed = required | set(FIELD_LIMITS) | {"emergency_contact_phone"}
    unknown = set(payload) - allowed
    if unknown:
        key = sorted(unknown)[0]
        raise FieldValidationError(key, f"The field '{key}' isn’t supported.")
    for field in allowed:
        if field not in payload:
            if not partial and field in required:
                raise FieldValidationError(field, f"Please provide {field.replace('_', ' ')}.")
            continue
        value = payload[field]
        if partial and field == "preferred_language" and (
            value is None or (isinstance(value, str) and not value.strip())
        ):
            result[field] = "English"
            continue
        if field in normalizers:
            if field in {"first_name", "last_name"}:
                value = normalize_name(field, value)
            else:
                value = normalizers[field](value)
        else:
            value = sanitize_string(field, value, required=(field in required))
        result[field] = value
    return result
