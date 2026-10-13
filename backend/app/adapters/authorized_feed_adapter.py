"""Authorized external device/hospital feed adapter contract.

Prepared for future authorized live data streams. Enforces cryptographic
authorization headers/signatures before admitting observations with
source_mode='authorized_feed'.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hmac
from typing import Any

from ..observation_contract import CanonicalObservation, ObservationUnits, VitalsMeasurements
from .base import BaseSourceAdapter


class AuthorizedFeedAdapter(BaseSourceAdapter):
    """Adapter for future authorized hospital/device feeds."""

    def __init__(self, source_name: str, feed_key: str | None = None) -> None:
        self._source_name = source_name
        self._feed_key = feed_key

    @property
    def source_name(self) -> str:
        return self._source_name

    @property
    def source_mode(self) -> str:
        return "authorized_feed"

    def transform(self, raw_data: dict[str, Any]) -> CanonicalObservation:
        # Fail closed until a per-feed secret is configured. Compare credentials
        # in constant time and never accept a caller-supplied key as its own trust root.
        auth_header = raw_data.get("feed_auth_key")
        if not self._feed_key or not auth_header or not hmac.compare_digest(
            str(auth_header), self._feed_key
        ):
            raise PermissionError("Unauthorized external device feed: missing or invalid feed credentials")

        observed_at = raw_data["observed_at"]
        if isinstance(observed_at, str):
            observed_at = datetime.fromisoformat(observed_at)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)

        vitals = VitalsMeasurements(**raw_data["measurements"])
        units = ObservationUnits(**raw_data.get("units", {}))

        return CanonicalObservation(
            source_system=self.source_name,
            source_event_id=str(raw_data["source_event_id"]),
            source_mode=self.source_mode,
            patient_id=str(raw_data["patient_id"]),
            observed_at=observed_at,
            measurements=vitals,
            units=units,
        )
