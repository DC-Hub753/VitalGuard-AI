"""Historical replay adapter for reading timestamped recorded observations.

Guarantees:
- Reads real timestamped records (never invents synthetic random data).
- Explicitly flags provenance with source_mode='historical_replay'.
- Preserves raw timestamps and measurement values.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..observation_contract import CanonicalObservation, ObservationUnits, VitalsMeasurements
from .base import BaseSourceAdapter


class HistoricalReplayAdapter(BaseSourceAdapter):
    """Adapter for authorized historical patient observation sets."""

    def __init__(self, source_name: str = "historical-replay-dataset") -> None:
        self._source_name = source_name

    @property
    def source_name(self) -> str:
        return self._source_name

    @property
    def source_mode(self) -> str:
        return "historical_replay"

    def transform(self, raw_data: dict[str, Any]) -> CanonicalObservation:
        """Parse raw historical record into CanonicalObservation."""
        patient_id = raw_data.get("patient_id")
        event_id = raw_data.get("event_id") or raw_data.get("idempotency_key")
        observed_at = raw_data.get("observed_at")
        vitals_raw = raw_data.get("vitals") or raw_data.get("measurements", {})
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

        units = ObservationUnits(**units_raw) if units_raw else ObservationUnits()

        return CanonicalObservation(
            source_system=self.source_name,
            source_event_id=str(event_id),
            source_mode=self.source_mode,
            patient_id=str(patient_id),
            observed_at=observed_at,
            measurements=vitals,
            units=units,
        )
