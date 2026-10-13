"""Canonical observation contract, physiological validation, and quality assessment.

Defines the validated schema for continuous patient vital observations.
Distinguishes physiologically implausible values from clinically abnormal values.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SourceMode = Literal["historical_replay", "synthetic_demo", "authorized_feed"]


class ObservationUnits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age: Literal["years"] | None = "years"
    heart_rate: Literal["bpm"] = "bpm"
    spo2: Literal["percent"] = "percent"
    systolic_bp: Literal["mmHg"] = "mmHg"
    diastolic_bp: Literal["mmHg"] = "mmHg"
    temperature: Literal["degC"] = "degC"
    respiratory_rate: Literal["breaths/min"] = "breaths/min"


class VitalsMeasurements(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    heart_rate: float = Field(ge=10.0, le=300.0, description="Heart rate in bpm")
    spo2: float = Field(ge=40.0, le=100.0, description="Oxygen saturation in percent")
    systolic_bp: float = Field(ge=40.0, le=300.0, description="Systolic blood pressure in mmHg")
    diastolic_bp: float = Field(ge=20.0, le=200.0, description="Diastolic blood pressure in mmHg")
    temperature: float = Field(ge=25.0, le=45.0, description="Core temperature in degC")
    respiratory_rate: float = Field(ge=3.0, le=80.0, description="Respiratory rate in breaths/min")
    age: int = Field(default=55, ge=0, le=125, description="Patient age in years")

    @model_validator(mode="after")
    def validate_pulse_pressure(self) -> VitalsMeasurements:
        if self.diastolic_bp >= self.systolic_bp:
            raise ValueError(
                f"diastolic_bp ({self.diastolic_bp}) must be strictly lower than systolic_bp ({self.systolic_bp})"
            )
        return self


# Physiological plausibility ranges (values outside these indicate sensor disconnect / corrupt transmission)
PHYSIOLOGICAL_BOUNDS = {
    "heart_rate": (20.0, 260.0),
    "spo2": (50.0, 100.0),
    "systolic_bp": (50.0, 260.0),
    "diastolic_bp": (30.0, 150.0),
    "temperature": (30.0, 43.0),
    "respiratory_rate": (4.0, 60.0),
}


class QualityAssessment(BaseModel):
    is_plausible: bool
    is_abnormal: bool
    warnings: list[str] = Field(default_factory=list)
    quality_score: float = Field(ge=0.0, le=1.0, default=1.0)


def evaluate_vitals_quality(vitals: VitalsMeasurements) -> QualityAssessment:
    """Evaluate physiological plausibility and clinical abnormalities."""
    warnings = []
    is_plausible = True
    is_abnormal = False

    values = {
        "heart_rate": vitals.heart_rate,
        "spo2": vitals.spo2,
        "systolic_bp": vitals.systolic_bp,
        "diastolic_bp": vitals.diastolic_bp,
        "temperature": vitals.temperature,
        "respiratory_rate": vitals.respiratory_rate,
    }

    # Check plausibility
    for param, (low, high) in PHYSIOLOGICAL_BOUNDS.items():
        val = values[param]
        if val < low or val > high:
            is_plausible = False
            warnings.append(f"{param} value {val} is physiologically implausible ({low}-{high})")

    # Check clinical abnormality thresholds
    if vitals.heart_rate < 50 or vitals.heart_rate > 110:
        is_abnormal = True
    if vitals.spo2 < 94:
        is_abnormal = True
    if vitals.systolic_bp < 90 or vitals.systolic_bp > 160:
        is_abnormal = True
    if vitals.temperature < 36.0 or vitals.temperature > 38.0:
        is_abnormal = True
    if vitals.respiratory_rate < 10 or vitals.respiratory_rate > 24:
        is_abnormal = True

    score = 1.0 if is_plausible else 0.4
    return QualityAssessment(
        is_plausible=is_plausible,
        is_abnormal=is_abnormal,
        warnings=warnings,
        quality_score=score,
    )


class CanonicalObservation(BaseModel):
    """Canonical observation contract for ingestion and real-time streaming."""
    model_config = ConfigDict(extra="forbid")

    source_system: str = Field(min_length=1, max_length=80)
    source_event_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    source_mode: SourceMode = "synthetic_demo"
    patient_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    observed_at: datetime
    measurements: VitalsMeasurements
    units: ObservationUnits = Field(default_factory=ObservationUnits)

    @field_validator("observed_at")
    @classmethod
    def require_tz(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone offset")
        now = datetime.now(timezone.utc)
        normalized = value.astimezone(timezone.utc)
        if normalized > now + timedelta(minutes=5):
            raise ValueError("observed_at cannot be in the future")
        return normalized
