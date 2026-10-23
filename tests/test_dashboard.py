"""Tests for the read-only patient dashboard route and safe rendering markers."""


def test_dashboard_returns_html_with_expected_markers(api_client) -> None:
    """The dashboard route serves its self-contained UI as HTML."""
    response = api_client.get("/dashboard")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    for marker in (
        "Patient dashboard",
        "Demo data only. Do not enter real patient information.",
        "No patients registered yet",
        "Search name or last 4 digits",
        "Refresh",
        'href="/docs"',
        'fetch("/patients"',
        "Preferred language",
        "Registered",
    ):
        assert marker in response.text


def test_dashboard_uses_text_content_and_omits_sensitive_columns(api_client) -> None:
    """Patient data is assigned as text and private fields are not rendered."""
    response = api_client.get("/dashboard")
    html = response.text

    assert "cell.textContent = value" in html
    assert "innerHTML" not in html
    assert "Intl.DateTimeFormat(undefined" in html
    assert 'timeStyle: "short"' in html
    assert "slice(-4)" in html

    for private_field in (
        "insurance_provider",
        "insurance_member_id",
        "address_line_1",
        "address_line_2",
        "emergency_contact_name",
        "emergency_contact_phone",
        "patient.email",
    ):
        assert private_field not in html
