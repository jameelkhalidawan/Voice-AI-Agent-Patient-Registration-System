"""End-to-end route tests against isolated temporary SQLite databases."""

from app.config import Settings, get_settings
from app.data.database import get_db
from app.main import app

TEST_KEY = "stage5-test-api-key"
HEADERS = {"X-API-Key": TEST_KEY}


def test_health_uses_success_envelope(api_client) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok"}, "error": None}


def test_create_get_and_partial_update(api_client, patient_payload) -> None:
    created = api_client.post("/patients", json=patient_payload, headers=HEADERS)
    assert created.status_code == 201
    body = created.json()
    assert body["error"] is None
    patient_id = body["data"]["patient_id"]
    assert body["data"]["state"] == "TX"

    fetched = api_client.get(f"/patients/{patient_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["patient_id"] == patient_id

    updated = api_client.put(
        f"/patients/{patient_id}",
        json={"email": "taylor@example.test"},
        headers=HEADERS,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["email"] == "taylor@example.test"
    assert updated.json()["data"]["first_name"] == "Taylor"


def test_list_filters_are_exact_case_insensitive(api_client, patient_payload) -> None:
    api_client.post("/patients", json=patient_payload, headers=HEADERS)
    assert len(api_client.get("/patients?last_name=mcdonald").json()["data"]) == 1
    assert api_client.get("/patients?last_name=Donald").json()["data"] == []
    assert len(api_client.get("/patients?date_of_birth=03%2F14%2F1990").json()["data"]) == 1
    assert len(api_client.get("/patients?phone_number=%28202%29-555-0198").json()["data"]) == 1


def test_missing_or_wrong_write_key_is_401(api_client, patient_payload) -> None:
    for headers in ({}, {"X-API-Key": "wrong-test-key"}):
        response = api_client.post("/patients", json=patient_payload, headers=headers)
        assert response.status_code == 401
        assert response.json()["data"] is None
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_unconfigured_write_key_is_503(api_client, patient_payload, monkeypatch) -> None:
    monkeypatch.setattr("app.api.security.get_settings", lambda: Settings(api_key=None))
    response = api_client.post("/patients", json=patient_payload, headers=HEADERS)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CONFIGURATION_ERROR"


def test_invalid_patient_is_422_with_field_message(api_client, patient_payload) -> None:
    patient_payload["state"] = "ZZ"
    response = api_client.post("/patients", json=patient_payload, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["data"] is None
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "state" in response.json()["error"]["fields"]


def test_malformed_request_is_400(api_client) -> None:
    response = api_client.get("/patients/not-a-uuid")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MALFORMED_REQUEST"


def test_not_found_is_404(api_client) -> None:
    response = api_client.get("/patients/00000000-0000-4000-8000-000000000001")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_duplicate_phone_is_409_on_create_and_update(api_client, patient_payload) -> None:
    first = api_client.post("/patients", json=patient_payload, headers=HEADERS).json()["data"]
    second_data = dict(patient_payload, phone_number="2025550187", first_name="Morgan")
    second = api_client.post("/patients", json=second_data, headers=HEADERS).json()["data"]

    create_duplicate = api_client.post("/patients", json=dict(patient_payload, first_name="Jordan"), headers=HEADERS)
    assert create_duplicate.status_code == 409
    assert create_duplicate.json()["error"]["code"] == "DUPLICATE_PHONE"

    update_duplicate = api_client.put(
        f"/patients/{second['patient_id']}",
        json={"phone_number": patient_payload["phone_number"]},
        headers=HEADERS,
    )
    assert update_duplicate.status_code == 409
    assert update_duplicate.json()["error"]["code"] == "DUPLICATE_PHONE"
    assert api_client.get(f"/patients/{first['patient_id']}").status_code == 200


def test_soft_delete_is_hidden_and_phone_can_be_reused(api_client, patient_payload) -> None:
    created = api_client.post("/patients", json=patient_payload, headers=HEADERS).json()["data"]
    patient_id = created["patient_id"]
    deleted = api_client.delete(f"/patients/{patient_id}", headers=HEADERS)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted_at"] is not None
    assert api_client.get(f"/patients/{patient_id}").status_code == 404
    assert api_client.get("/patients?phone_number=2025550198").json()["data"] == []

    replacement = api_client.post("/patients", json=patient_payload, headers=HEADERS)
    assert replacement.status_code == 201
    assert replacement.json()["data"]["patient_id"] != patient_id


def test_oversized_request_is_413(api_client) -> None:
    response = api_client.post("/patients", content="x" * 70000)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_rate_limit_is_429(api_client, monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    get_settings.cache_clear()
    assert api_client.get("/health").status_code == 200
    response = api_client.get("/health")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


def test_unexpected_error_is_generic_500(api_client, monkeypatch) -> None:
    def broken_db_dependency():
        raise RuntimeError("test secret detail must not reach the caller")

    app.dependency_overrides[get_db] = broken_db_dependency
    response = api_client.get("/patients")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "test secret detail" not in response.text
