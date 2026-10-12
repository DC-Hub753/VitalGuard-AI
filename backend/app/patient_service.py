"""Persistence helpers for patient records in the synthetic VitalGuard demo.

Follows the same engine-per-call pattern as alert_service.py and storage.py.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import insert, select, update, func
from sqlalchemy.exc import IntegrityError

from .storage import _engine, _ensure_schema
from .storage_schema import patients


def _serialize(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("created_at", "updated_at"):
        if item.get(key) is not None and hasattr(item[key], "isoformat"):
            item[key] = item[key].isoformat()
    return item


def create_patient(
    *,
    patient_id: str,
    display_name: str,
    sex: str = "U",
    date_of_birth: str | None = None,
    ward: str = "General Ward",
    bed: str = "",
    created_by: str = "demo-system",
) -> dict[str, Any]:
    """Create a new patient record. Raises IntegrityError on duplicate patient_id."""
    engine = _engine()
    try:
        with engine.begin() as connection:
            connection.execute(insert(patients).values(
                patient_id=patient_id,
                display_name=display_name,
                sex=sex,
                date_of_birth=date_of_birth,
                ward=ward,
                bed=bed,
                created_by=created_by,
            ))
            row = connection.execute(
                select(patients).where(patients.c.patient_id == patient_id)
            ).mappings().one()
        return _serialize(row)
    finally:
        engine.dispose()


def get_patient(patient_id: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
    """Return a single patient by ID, or None if not found."""
    engine = _engine()
    try:
        query = select(patients).where(patients.c.patient_id == patient_id)
        if not include_inactive:
            query = query.where(patients.c.active == True)  # noqa: E712
        with engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        return _serialize(row) if row else None
    finally:
        engine.dispose()


def list_patients(
    *,
    active_only: bool = True,
    ward: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Return a page of patients and the total matching count."""
    engine = _engine()
    try:
        query = select(patients)
        count_query = select(func.count()).select_from(patients)
        if active_only:
            query = query.where(patients.c.active == True)  # noqa: E712
            count_query = count_query.where(patients.c.active == True)  # noqa: E712
        if ward is not None:
            query = query.where(patients.c.ward == ward)
            count_query = count_query.where(patients.c.ward == ward)

        query = query.order_by(patients.c.patient_id).limit(limit).offset(offset)
        with engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
            total = connection.execute(count_query).scalar()
        return [_serialize(row) for row in rows], total or 0
    finally:
        engine.dispose()


def update_patient(patient_id: str, *, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Apply partial updates to a patient. Returns the updated patient or None."""
    if not updates:
        return get_patient(patient_id)
    engine = _engine()
    try:
        with engine.begin() as connection:
            # Only update an active patient.
            existing = connection.execute(
                select(patients).where(
                    patients.c.patient_id == patient_id,
                    patients.c.active == True,  # noqa: E712
                )
            ).mappings().first()
            if not existing:
                return None

            connection.execute(
                update(patients)
                .where(patients.c.patient_id == patient_id)
                .values(**updates)
            )
            row = connection.execute(
                select(patients).where(patients.c.patient_id == patient_id)
            ).mappings().one()
        return _serialize(row)
    finally:
        engine.dispose()


def deactivate_patient(patient_id: str) -> dict[str, Any] | None:
    """Soft-delete: set active=False. Returns the deactivated patient or None."""
    engine = _engine()
    try:
        with engine.begin() as connection:
            existing = connection.execute(
                select(patients).where(patients.c.patient_id == patient_id)
            ).mappings().first()
            if not existing:
                return None
            if not existing["active"]:
                return _serialize(existing)
            connection.execute(
                update(patients)
                .where(patients.c.patient_id == patient_id)
                .values(active=False)
            )
            row = connection.execute(
                select(patients).where(patients.c.patient_id == patient_id)
            ).mappings().one()
        return _serialize(row)
    finally:
        engine.dispose()
