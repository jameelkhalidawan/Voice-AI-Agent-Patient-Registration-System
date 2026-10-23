"""Regression tests for Stage 3 field validation decisions."""

from datetime import date

import pytest

from app.services.validation import (
    FieldValidationError,
    normalize_dob,
    normalize_name,
    validate_patient_payload,
)


@pytest.mark.parametrize("name", ["O'Brien", "McDonald", "SMITH-JONES", "van der Meer"])
def test_names_preserve_meaningful_capitalization(name: str) -> None:
    assert normalize_name("last_name", name) == name


def test_name_trims_and_collapses_spaces_without_case_change() -> None:
    assert normalize_name("first_name", "  mCdonald   Ann ") == "mCdonald Ann"


@pytest.mark.parametrize("value", ["Anne3", "O'Brien2", "<b>Sam</b>"])
def test_name_rejects_digits_and_markup(value: str) -> None:
    with pytest.raises(FieldValidationError):
        normalize_name("first_name", value)


def test_exact_120_year_dob_boundary_on_leap_day() -> None:
    today = date(2024, 2, 29)
    assert normalize_dob(date(1904, 2, 29), today=today) == date(1904, 2, 29)
    with pytest.raises(FieldValidationError, match="older than 120"):
        normalize_dob(date(1904, 2, 28), today=today)


def test_february_28_nonleap_boundary() -> None:
    today = date(2025, 2, 28)
    assert normalize_dob(date(1905, 2, 28), today=today) == date(1905, 2, 28)
    with pytest.raises(FieldValidationError, match="older than 120"):
        normalize_dob(date(1904, 2, 29), today=today)


def test_empty_optional_partial_values_clear_nullable_fields() -> None:
    result = validate_patient_payload(
        {"email": " ", "address_line_2": None, "insurance_provider": "", "emergency_contact_phone": ""},
        partial=True,
    )
    assert result == {
        "email": None,
        "address_line_2": None,
        "insurance_provider": None,
        "emergency_contact_phone": None,
    }


def test_empty_required_partial_value_is_rejected() -> None:
    with pytest.raises(FieldValidationError) as error:
        validate_patient_payload({"city": "  "}, partial=True)
    assert error.value.field == "city"


def test_empty_language_resets_to_default() -> None:
    assert validate_patient_payload({"preferred_language": ""}, partial=True) == {
        "preferred_language": "English"
    }
