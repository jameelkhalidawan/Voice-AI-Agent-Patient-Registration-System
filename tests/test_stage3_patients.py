"""Regression tests for Stage 3 persistence and uniqueness behavior."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.data import models  # noqa: F401
from app.data.database import Base
from app.data.models import Patient
from app.services.patients import (
    DuplicatePhoneError,
    PatientService,
)


def test_last_name_filter_is_exact_case_insensitive(db_session, patient_payload) -> None:
    service = PatientService(db_session)
    service.create(patient_payload)
    assert len(service.list(last_name="mcdonald")) == 1
    assert service.list(last_name="Donald") == []
    assert service.list(last_name="Mc%") == []


def test_soft_deleted_patient_is_hidden_and_phone_can_be_reused(db_session, patient_payload) -> None:
    service = PatientService(db_session)
    old_patient = service.create(patient_payload)
    service.soft_delete(old_patient.patient_id)

    assert service.list(phone_number="202-555-0198") == []
    assert service.find_by_phone("2025550198") is None

    replacement = service.create(patient_payload)
    assert replacement.patient_id != old_patient.patient_id
    assert db_session.scalar(select(func.count()).select_from(Patient)) == 2


def test_active_phone_unique_constraint_is_enforced_by_database(db_session, patient_payload) -> None:
    service = PatientService(db_session)
    service.create(patient_payload)
    duplicate = dict(patient_payload, first_name="Jordan")
    with pytest.raises(DuplicatePhoneError):
        service.create(duplicate)


def test_unrelated_integrity_error_is_not_reported_as_duplicate(db_session, patient_payload, monkeypatch) -> None:
    service = PatientService(db_session)
    patient = service.create(patient_payload)
    monkeypatch.setattr(
        db_session,
        "commit",
        lambda: (_ for _ in ()).throw(IntegrityError("UPDATE", {}, RuntimeError("other constraint"))),
    )
    with pytest.raises(IntegrityError, match="other constraint"):
        service.update(patient.patient_id, {"email": "test@example.com"})


def test_concurrent_creates_cannot_both_claim_same_active_phone(tmp_path, patient_payload) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent-create.db'}",
        connect_args={"check_same_thread": False, "timeout": 20},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    barrier = Barrier(2)

    def attempt(first_name: str) -> str:
        with factory() as session:
            original_commit = session.commit

            def synchronized_commit() -> None:
                barrier.wait(timeout=10)
                original_commit()

            session.commit = synchronized_commit  # type: ignore[method-assign]
            payload = dict(patient_payload, first_name=first_name)
            try:
                PatientService(session).create(payload)
                return "created"
            except DuplicatePhoneError:
                return "duplicate"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ["Casey", "Riley"]))
        assert sorted(results) == ["created", "duplicate"]
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Patient)) == 1
    finally:
        engine.dispose()


def test_concurrent_updates_cannot_both_claim_same_active_phone(tmp_path, patient_payload) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent-update.db'}",
        connect_args={"check_same_thread": False, "timeout": 20},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        service = PatientService(session)
        first = service.create(patient_payload)
        second_data = dict(patient_payload, phone_number="2025550187", first_name="Morgan")
        second = service.create(second_data)
        first_id, second_id = first.patient_id, second.patient_id

    barrier = Barrier(2)

    def attempt(patient_id) -> str:
        with factory() as session:
            original_commit = session.commit

            def synchronized_commit() -> None:
                barrier.wait(timeout=10)
                original_commit()

            session.commit = synchronized_commit  # type: ignore[method-assign]
            try:
                PatientService(session).update(patient_id, {"phone_number": "2025550176"})
                return "updated"
            except DuplicatePhoneError:
                return "duplicate"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [first_id, second_id]))
        assert sorted(results) == ["duplicate", "updated"]
        with factory() as session:
            count = session.scalar(
                select(func.count()).select_from(Patient).where(Patient.phone_number == "2025550176")
            )
            assert count == 1
    finally:
        engine.dispose()
