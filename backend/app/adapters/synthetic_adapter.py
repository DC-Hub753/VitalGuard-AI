"""Synthetic demo adapter for synthetic simulated observations."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..observation_contract import CanonicalObservation, ObservationUnits, VitalsMeasurements
from .base import BaseSourceAdapter


class SyntheticDemoAdapter(BaseSourceAdapter):
    """Adapter for synthetic demonstration feeds."""

    def __init__(self, source_name: str = "synthetic-demo") -> None:
        self._source_name = source_name

    @property
    def source_name(self) -> str:
        return self._source_name

    @property
    def source_mode(self) -> str:
        return "synthetic_demo"

    def transform(self, raw_data: dict[str, Any]) -> CanonicalObservation:
        patient_id = raw_data.get("patient_id") or raw_data.get("observation", {}).get("patient_id")
        event_id = raw_data.get("source_event_id") or raw_data.get("idempotency_key")
        observed_at = raw_data.get("observed_at")
        vitals_raw = raw_data.get("observation") or raw_data.get("measurements", {})
        units_raw = raw_data.get("units", {})

        if isinstance(observed_at, str):
            observed_at = datetime.fromisoformat(observed_at)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)

        vitals = VitalsMeasurements(
            heart_rate=float(vitals_raw["heart_rate"]),
            spo2=float(vitals_raw["spo2"]),
            systolic_bp=float(vitals_raw["systolic_bp"]),
            diastolic_bp=float(vitals_raw["diastolic_bp"]),
            temperature=float(vitals_raw["temperature"]),
            respiratory_rate=float(vitals_raw["respiratory_rate"]),
            age=int(vitals_raw.get("age", 55)),
        )

        units = ObservationUnits(
            heart_rate=units_raw.get("heart_rate", "bpm"),
            spo2=units_raw.get("spo2", "percent"),
            systolic_bp=units_raw.get("systolic_bp", "mmHg"),
            diastolic_bp=units_raw.get("diastolic_bp", "mmHg"),
            temperature=units_raw.get("temperature", "degC"),
            respiratory_rate=units_raw.get("respiratory_rate", "breaths/min"),
        )

        return CanonicalObservation(
            source_system=self.source_name,
            source_event_id=str(event_id),
            source_mode=self.source_mode,
            patient_id=str(patient_id),
            observed_at=observed_at,
            measurements=vitals,
            units=units,
        )
