"""Transactional persistence for validated ingestion records and event replay."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import desc, func, insert, select
from sqlalchemy.exc import IntegrityError

from .ingestion_schema import ingestion_records
from .storage import _OBSERVATIONS, _engine
from .storage_schema import patients


def persist_ingested_observation(
    *,
    source_system: str,
    source_event_id: str,
    patient_id: str,
    observed_at: datetime,
    units: dict[str, str],
    payload_hash: str,
    inputs: dict,
    prediction: dict,
    source_mode: str = "synthetic_demo",
    quality: dict | None = None,
    require_known_patient: bool = False,
) -> dict[str, Any]:
    """Persist observation and provenance together with source-event idempotency and ordering diagnostics."""
    engine = _engine()
    quality_dict = dict(quality) if quality else {}
    try:
        try:
            with engine.begin() as connection:
                # 1. Patient existence validation if required
                if require_known_patient:
                    exists = connection.execute(
                        select(patients.c.patient_id).where(patients.c.patient_id == patient_id)
                    ).scalar()
                    if not exists:
                        return {
                            "status": "rejected",
                            "diagnostic": "patient_not_found",
                            "message": f"Patient '{patient_id}' not found in registry",
                        }

                # 2. Idempotency check
                existing = connection.execute(
                    select(ingestion_records).where(
                        ingestion_records.c.source_system == source_system,
                        ingestion_records.c.source_event_id == source_event_id,
                    )
                ).mappings().first()
                if existing:
                    return {
                        "status": "duplicate" if existing["payload_hash"] == payload_hash else "conflict",
                        "observation_id": existing["observation_id"],
                        "ingestion_id": existing["id"],
                        "source_mode": existing["source_mode"],
                    }

                # 3. Out-of-order check
                latest_observed = connection.execute(
                    select(func.max(ingestion_records.c.observed_at)).where(
                        ingestion_records.c.patient_id == patient_id
                    )
                ).scalar()
                if latest_observed is not None:
                    # Normalize timezones for comparison
                    latest_tz = latest_observed.replace(tzinfo=timezone.utc) if latest_observed.tzinfo is None else latest_observed
                    current_tz = observed_at.replace(tzinfo=timezone.utc) if observed_at.tzinfo is None else observed_at
                    if current_tz < latest_tz:
                        quality_dict["out_of_order"] = True
                        warnings = quality_dict.setdefault("warnings", [])
                        warnings.append(
                            f"Observation arrived out of order (observed_at {current_tz.isoformat()} < latest {latest_tz.isoformat()})"
                        )

                # 4. Insert into observations table
                observation_result = connection.execute(insert(_OBSERVATIONS).values(
                    patient_id=patient_id,
                    input_json=json.dumps(inputs, separators=(",", ":")),
                    prediction_json=json.dumps(prediction, separators=(",", ":")),
                    model_version=prediction.get("model_version", "unknown"),
                ))
                observation_id = observation_result.inserted_primary_key[0]

                # 5. Insert into ingestion_records table
                ingestion_result = connection.execute(insert(ingestion_records).values(
                    source_system=source_system,
                    source_event_id=source_event_id,
                    source_mode=source_mode,
                    patient_id=patient_id,
                    observed_at=observed_at,
                    observation_id=observation_id,
                    units_json=json.dumps(units, separators=(",", ":"), sort_keys=True),
                    quality_json=json.dumps(quality_dict, separators=(",", ":"), sort_keys=True),
                    payload_hash=payload_hash,
                ))
                return {
                    "status": "accepted",
                    "observation_id": observation_id,
                    "ingestion_id": ingestion_result.inserted_primary_key[0],
                    "source_mode": source_mode,
                    "out_of_order": quality_dict.get("out_of_order", False),
                    "quality": quality_dict,
                }
        except IntegrityError:
            # Handle race condition on unique constraint
            with engine.connect() as connection:
                existing = connection.execute(
                    select(ingestion_records).where(
                        ingestion_records.c.source_system == source_system,
                        ingestion_records.c.source_event_id == source_event_id,
                    )
                ).mappings().first()
            if existing:
                return {
                    "status": "duplicate" if existing["payload_hash"] == payload_hash else "conflict",
                    "observation_id": existing["observation_id"],
                    "ingestion_id": existing["id"],
                    "source_mode": existing["source_mode"],
                }
            raise
    finally:
        engine.dispose()


def list_replayable_events(
    *,
    patient_id: str | None = None,
    after_event_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query persisted ingestion records in ascending order to support reconnection event recovery."""
    engine = _engine()
    try:
        query = select(
            ingestion_records.c.id.label("event_id"),
            ingestion_records.c.observation_id,
            ingestion_records.c.patient_id,
            ingestion_records.c.source_system,
            ingestion_records.c.source_mode,
            ingestion_records.c.observed_at,
            ingestion_records.c.received_at,
            ingestion_records.c.quality_json,
            _OBSERVATIONS.c.input_json,
            _OBSERVATIONS.c.prediction_json,
        ).select_from(
            ingestion_records.join(_OBSERVATIONS, ingestion_records.c.observation_id == _OBSERVATIONS.c.id)
        )

        if patient_id is not None:
            query = query.where(ingestion_records.c.patient_id == patient_id)
        if after_event_id is not None:
            query = query.where(ingestion_records.c.id > after_event_id)

        query = query.order_by(ingestion_records.c.id.asc()).limit(limit)

        with engine.connect() as connection:
            rows = connection.execute(query).mappings().all()

        events = []
        for r in rows:
            observed_at_str = r["observed_at"].isoformat() if hasattr(r["observed_at"], "isoformat") else str(r["observed_at"])
            events.append({
                "type": "observation.created",
                "event_id": r["event_id"],
                "observation_id": r["observation_id"],
                "patient_id": r["patient_id"],
                "source_system": r["source_system"],
                "source_mode": r["source_mode"],
                "observed_at": observed_at_str,
                "observation": json.loads(r["input_json"]) if r["input_json"] else {},
                "prediction": json.loads(r["prediction_json"]) if r["prediction_json"] else {},
                "quality": json.loads(r["quality_json"]) if r["quality_json"] else {},
            })
        return events
    finally:
        engine.dispose()


def get_patient_freshness(
    patient_id: str,
    *,
    stale_threshold_seconds: int = 300,
) -> dict[str, Any]:
    """Calculate data freshness and provenance status for a given patient."""
    engine = _engine()
    try:
        with engine.connect() as connection:
            record = connection.execute(
                select(ingestion_records)
                .where(ingestion_records.c.patient_id == patient_id)
                .order_by(desc(ingestion_records.c.observed_at))
                .limit(1)
            ).mappings().first()

        if not record:
            return {
                "patient_id": patient_id,
                "status": "disconnected",
                "freshness": "stale",
                "has_data": False,
                "source_mode": "none",
                "source_system": "none",
                "latest_observed_at": None,
                "age_seconds": None,
                "stale_threshold_seconds": stale_threshold_seconds,
            }

        observed_at = record["observed_at"]
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_seconds = max(0.0, (now - observed_at).total_seconds())

        is_fresh = age_seconds <= stale_threshold_seconds
        freshness_status = "fresh" if is_fresh else "stale"
        connection_status = "connected" if is_fresh else "stale"

        return {
            "patient_id": patient_id,
            "status": connection_status,
            "freshness": freshness_status,
            "has_data": True,
            "source_mode": record["source_mode"],
            "source_system": record["source_system"],
            "latest_observed_at": observed_at.isoformat(),
            "age_seconds": round(age_seconds, 1),
            "stale_threshold_seconds": stale_threshold_seconds,
        }
    finally:
        engine.dispose()
