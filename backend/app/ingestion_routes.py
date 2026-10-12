"""Validated, idempotent observation ingestion, historical replay, and provenance streaming."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .adapters.replay_adapter import HistoricalReplayAdapter
from .adapters.synthetic_adapter import SyntheticDemoAdapter
from .alert_service import create_alert
from .auth import authenticate_principal, require_permission
from .ingestion_store import get_patient_freshness, list_replayable_events, persist_ingested_observation
from .live_events import hub
from .model import MODEL_VERSION, explain, predict_probability, risk_level
from .observation_contract import (
    CanonicalObservation,
    ObservationUnits,
    VitalsMeasurements,
    evaluate_vitals_quality,
)
from .permissions import PERM_OBSERVATIONS_CREATE, PERM_OBSERVATIONS_READ
from .schemas import RiskPrediction, VitalInput

router = APIRouter(
    prefix="/api/v1/ingestion",
    tags=["validated-ingestion"],
    dependencies=[Depends(authenticate_principal)],
)


class IngestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_system: Literal["synthetic-demo"] = "synthetic-demo"
    source_event_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    observed_at: datetime
    observation: VitalInput
    units: ObservationUnits

    @field_validator("observed_at")
    @classmethod
    def require_timezone_and_reasonable_window(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone offset")
        now = datetime.now(timezone.utc)
        normalized = value.astimezone(timezone.utc)
        if normalized > now + timedelta(minutes=5):
            raise ValueError("observed_at cannot be more than 5 minutes in the future")
        if normalized < now - timedelta(days=30):
            raise ValueError("observed_at is outside the 30-day demo ingestion window")
        return normalized

    @model_validator(mode="after")
    def enforce_synthetic_patient_id(self):
        if not self.observation.patient_id.startswith("DEMO-"):
            raise ValueError("Only synthetic demo patient IDs beginning with DEMO- are accepted")
        return self


class IngestionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    records: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class ReplayBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_name: str = Field(default="historical-dataset-replay", min_length=1, max_length=80)
    records: list[dict[str, Any]] = Field(min_length=1, max_length=200)


def _error_detail(error: ValidationError) -> list[dict[str, str]]:
    return [
        {"field": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
        for item in error.errors(include_url=False, include_context=False)
    ]


def _process_and_persist_observation(
    *,
    source_system: str,
    source_event_id: str,
    source_mode: str,
    patient_id: str,
    observed_at: datetime,
    vitals: VitalsMeasurements,
    units: ObservationUnits,
    require_known_patient: bool = False,
    reject_implausible: bool = False,
) -> dict[str, Any]:
    """Core assessment, persistence and diagnostic evaluation."""
    quality_assessment = evaluate_vitals_quality(vitals)
    if reject_implausible and not quality_assessment.is_plausible:
        return {
            "status": "rejected",
            "diagnostic": "physiologically_implausible",
            "warnings": quality_assessment.warnings,
        }

    values = {
        "heart_rate": vitals.heart_rate,
        "spo2": vitals.spo2,
        "systolic_bp": vitals.systolic_bp,
        "diastolic_bp": vitals.diastolic_bp,
        "temperature": vitals.temperature,
        "respiratory_rate": vitals.respiratory_rate,
        "age": vitals.age,
    }

    probability = predict_probability(values)
    score = round(probability * 100)
    level = risk_level(score)

    prediction = RiskPrediction(
        patient_id=patient_id,
        risk_score=score,
        risk_level=level,
        model_probability=round(probability, 4),
        factors=explain(values),
        model_version=MODEL_VERSION,
    )

    canonical_repr = {
        "source_system": source_system,
        "source_event_id": source_event_id,
        "source_mode": source_mode,
        "patient_id": patient_id,
        "observed_at": observed_at.isoformat(),
        "vitals": values,
        "units": units.model_dump(),
    }
    payload_hash = hashlib.sha256(
        json.dumps(canonical_repr, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    quality_metadata = {
        "is_plausible": quality_assessment.is_plausible,
        "is_abnormal": quality_assessment.is_abnormal,
        "quality_score": quality_assessment.quality_score,
        "warnings": quality_assessment.warnings,
    }

    persisted = persist_ingested_observation(
        source_system=source_system,
        source_event_id=source_event_id,
        patient_id=patient_id,
        observed_at=observed_at,
        units=units.model_dump(),
        payload_hash=payload_hash,
        inputs=values,
        prediction=prediction.model_dump(),
        source_mode=source_mode,
        quality=quality_metadata,
        require_known_patient=require_known_patient,
    )

    return {
        **persisted,
        "source_system": source_system,
        "source_event_id": source_event_id,
        "source_mode": source_mode,
        "patient_id": patient_id,
        "observed_at": observed_at.isoformat(),
        "prediction": prediction.model_dump(),
        "values": values,
    }


@router.post("/batch")
async def ingest_batch(
    batch: IngestionBatch,
    principal: dict = Depends(require_permission(PERM_OBSERVATIONS_CREATE)),
):
    """Validate each item independently; valid items commit even when peers fail."""
    results: list[dict[str, Any]] = []
    events_to_broadcast: list[dict[str, Any]] = []

    for index, raw in enumerate(batch.records):
        try:
            item = IngestionItem.model_validate(raw)
        except ValidationError as error:
            results.append({"index": index, "status": "rejected", "errors": _error_detail(error)})
            continue

        vitals = VitalsMeasurements(
            heart_rate=item.observation.heart_rate,
            spo2=item.observation.spo2,
            systolic_bp=item.observation.systolic_bp,
            diastolic_bp=item.observation.diastolic_bp,
            temperature=item.observation.temperature,
            respiratory_rate=item.observation.respiratory_rate,
            age=item.observation.age,
        )

        res = _process_and_persist_observation(
            source_system=item.source_system,
            source_event_id=item.source_event_id,
            source_mode="synthetic_demo",
            patient_id=item.observation.patient_id,
            observed_at=item.observed_at,
            vitals=vitals,
            units=item.units,
            require_known_patient=False,
            reject_implausible=False,
        )

        res["index"] = index
        res["demo_only"] = True
        results.append(res)

        if res["status"] == "accepted":
            events_to_broadcast.append({
                "type": "observation.created",
                "event_id": res["observation_id"],
                "observation_id": res["observation_id"],
                "patient_id": item.observation.patient_id,
                "observed_at": item.observed_at.isoformat(),
                "source_system": item.source_system,
                "source_mode": "synthetic_demo",
                "observation": res["values"],
                "prediction": res["prediction"],
                "demo_only": True,
            })
            # Check alert condition
            score = res["prediction"]["risk_score"]
            if score >= 65:
                lvl = res["prediction"]["risk_level"]
                alert = create_alert(
                    patient_id=item.observation.patient_id,
                    event_key=f"observation:{res['observation_id']}:elevated-risk",
                    severity="critical" if lvl == "critical" else "high",
                    title=f"{lvl.title()} demo risk score",
                    details={"observation_id": res["observation_id"], "risk_score": score, "risk_level": lvl},
                )
                if alert:
                    events_to_broadcast.append({
                        "type": "alert.created",
                        "event_id": alert["id"],
                        "patient_id": item.observation.patient_id,
                        "alert": alert,
                        "demo_only": True,
                    })

    # Broadcast events ONLY after all DB transactions have succeeded
    for evt in events_to_broadcast:
        await hub.broadcast(evt)

    accepted = sum(result["status"] == "accepted" for result in results)
    duplicates = sum(result["status"] == "duplicate" for result in results)
    conflicts = sum(result["status"] == "conflict" for result in results)
    rejected = sum(result["status"] == "rejected" for result in results) + conflicts
    return {
        "items": results,
        "count": len(results),
        "accepted": accepted,
        "duplicates": duplicates,
        "conflicts": conflicts,
        "rejected": rejected,
        "demo_only": True,
        "disclaimer": "Synthetic demo ingestion only. No real patient data or clinical use is authorized.",
    }


@router.post("/observation")
async def ingest_canonical_observation(
    observation: CanonicalObservation,
    require_known_patient: bool = Query(default=False),
    reject_implausible: bool = Query(default=False),
    principal: dict = Depends(require_permission(PERM_OBSERVATIONS_CREATE)),
):
    """Ingest a single canonical observation adhering to the strict contract."""
    res = _process_and_persist_observation(
        source_system=observation.source_system,
        source_event_id=observation.source_event_id,
        source_mode=observation.source_mode,
        patient_id=observation.patient_id,
        observed_at=observation.observed_at,
        vitals=observation.measurements,
        units=observation.units,
        require_known_patient=require_known_patient,
        reject_implausible=reject_implausible,
    )

    if res["status"] == "accepted":
        evt = {
            "type": "observation.created",
            "event_id": res["observation_id"],
            "observation_id": res["observation_id"],
            "patient_id": observation.patient_id,
            "observed_at": observation.observed_at.isoformat(),
            "source_system": observation.source_system,
            "source_mode": observation.source_mode,
            "observation": res["values"],
            "prediction": res["prediction"],
            "quality": res.get("quality", {}),
        }
        await hub.broadcast(evt)

        # Alert evaluation
        score = res["prediction"]["risk_score"]
        if score >= 65:
            lvl = res["prediction"]["risk_level"]
            alert = create_alert(
                patient_id=observation.patient_id,
                event_key=f"observation:{res['observation_id']}:elevated-risk",
                severity="critical" if lvl == "critical" else "high",
                title=f"{lvl.title()} risk score",
                details={"observation_id": res["observation_id"], "risk_score": score, "risk_level": lvl},
            )
            if alert:
                await hub.broadcast({
                    "type": "alert.created",
                    "event_id": alert["id"],
                    "patient_id": observation.patient_id,
                    "alert": alert,
                })

    return res


@router.post("/replay")
async def ingest_historical_replay(
    batch: ReplayBatchRequest,
    principal: dict = Depends(require_permission(PERM_OBSERVATIONS_CREATE)),
):
    """Ingest actual timestamped historical records with explicit 'historical_replay' provenance.

    Does not fabricate random data. Replay values are tagged and preserved with true historical timestamps.
    """
    adapter = HistoricalReplayAdapter(source_name=batch.source_name)
    results: list[dict[str, Any]] = []
    events_to_broadcast: list[dict[str, Any]] = []

    for index, raw in enumerate(batch.records):
        try:
            canonical = adapter.transform(raw)
        except Exception as exc:
            results.append({"index": index, "status": "rejected", "diagnostic": "schema_error", "message": str(exc)})
            continue

        res = _process_and_persist_observation(
            source_system=canonical.source_system,
            source_event_id=canonical.source_event_id,
            source_mode="historical_replay",
            patient_id=canonical.patient_id,
            observed_at=canonical.observed_at,
            vitals=canonical.measurements,
            units=canonical.units,
            require_known_patient=False,
            reject_implausible=False,
        )
        res["index"] = index
        results.append(res)

        if res["status"] == "accepted":
            events_to_broadcast.append({
                "type": "observation.created",
                "event_id": res["observation_id"],
                "observation_id": res["observation_id"],
                "patient_id": canonical.patient_id,
                "observed_at": canonical.observed_at.isoformat(),
                "source_system": canonical.source_system,
                "source_mode": "historical_replay",
                "observation": res["values"],
                "prediction": res["prediction"],
                "is_replay": True,
            })

    for evt in events_to_broadcast:
        await hub.broadcast(evt)

    accepted = sum(r["status"] == "accepted" for r in results)
    duplicates = sum(r["status"] == "duplicate" for r in results)
    conflicts = sum(r["status"] == "conflict" for r in results)
    rejected = sum(r["status"] == "rejected" for r in results) + conflicts

    return {
        "items": results,
        "count": len(results),
        "accepted": accepted,
        "duplicates": duplicates,
        "conflicts": conflicts,
        "rejected": rejected,
        "source_mode": "historical_replay",
        "provenance_note": "Explicitly labeled historical replay data; never presented as live clinical feed.",
    }


@router.get("/freshness/{patient_id}")
def check_patient_freshness(
    patient_id: str,
    stale_threshold_seconds: int = Query(default=300, ge=0, le=86400),
    principal: dict = Depends(require_permission(PERM_OBSERVATIONS_READ)),
):
    """Expose data freshness, latest observation timestamp, and source provenance."""
    return get_patient_freshness(patient_id, stale_threshold_seconds=stale_threshold_seconds)


@router.get("/events")
def get_replayable_events(
    patient_id: str | None = Query(default=None, min_length=1, max_length=64),
    after_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    principal: dict = Depends(require_permission(PERM_OBSERVATIONS_READ)),
):
    """Replay past persisted events for recovering missed state after network disconnection or restart."""
    events = list_replayable_events(patient_id=patient_id, after_event_id=after_id, limit=limit)
    return {
        "events": events,
        "count": len(events),
        "after_id": after_id,
        "limit": limit,
    }
