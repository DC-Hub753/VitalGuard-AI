"""Temporal and physiological feature extraction for VitalGuard risk models.

Computes rates of change and physiological derived parameters strictly from
observations available up to the current prediction time (no future leakage).
"""
from __future__ import annotations

from typing import Any


def derive_physiological_features(vitals: dict[str, float]) -> dict[str, float]:
    """Derive instantaneous hemodynamic ratios from current vital signs."""
    hr = float(vitals.get("heart_rate", 80.0))
    sys = float(vitals.get("systolic_bp", 120.0))
    dia = float(vitals.get("diastolic_bp", 80.0))

    # Shock index: HR / Systolic BP (normal: 0.5 - 0.7; > 0.9 indicates occult shock)
    shock_index = round(hr / max(sys, 40.0), 3)

    # Pulse pressure: Systolic BP - Diastolic BP (normal: 30 - 50 mmHg)
    pulse_pressure = round(max(sys - dia, 0.0), 1)

    # Mean arterial pressure (MAP): Diastolic BP + 1/3(Systolic BP - Diastolic BP)
    map_pressure = round(dia + (sys - dia) / 3.0, 1)

    return {
        "shock_index": shock_index,
        "pulse_pressure": pulse_pressure,
        "mean_arterial_pressure": map_pressure,
    }


def compute_temporal_trends(
    current_vitals: dict[str, float],
    prior_observations: list[dict[str, Any]] | None = None,
) -> dict[str, float]:
    """Calculate rate of change over the observation window.

    Prior observations must be chronologically ordered before current vitals.
    """
    trends = {
        "hr_trend_30m": 0.0,
        "spo2_trend_30m": 0.0,
        "rr_trend_30m": 0.0,
        "sys_trend_30m": 0.0,
    }

    if not prior_observations:
        return trends

    # Take the most recent prior observation
    prior = prior_observations[0]
    prior_inputs = prior.get("observation") or prior.get("input_json") or prior

    if isinstance(prior_inputs, dict):
        if "heart_rate" in prior_inputs:
            trends["hr_trend_30m"] = round(float(current_vitals.get("heart_rate", 0)) - float(prior_inputs["heart_rate"]), 1)
        if "spo2" in prior_inputs:
            trends["spo2_trend_30m"] = round(float(current_vitals.get("spo2", 0)) - float(prior_inputs["spo2"]), 1)
        if "respiratory_rate" in prior_inputs:
            trends["rr_trend_30m"] = round(float(current_vitals.get("respiratory_rate", 0)) - float(prior_inputs["respiratory_rate"]), 1)
        if "systolic_bp" in prior_inputs:
            trends["sys_trend_30m"] = round(float(current_vitals.get("systolic_bp", 0)) - float(prior_inputs["systolic_bp"]), 1)

    return trends


def build_full_feature_vector(
    vitals: dict[str, float],
    prior_observations: list[dict[str, Any]] | None = None,
) -> dict[str, float]:
    """Combine base vitals, physiological ratios, and temporal trend features."""
    physio = derive_physiological_features(vitals)
    temporal = compute_temporal_trends(vitals, prior_observations)

    features = {
        "age": float(vitals.get("age", 55.0)),
        "heart_rate": float(vitals.get("heart_rate", 80.0)),
        "spo2": float(vitals.get("spo2", 98.0)),
        "systolic_bp": float(vitals.get("systolic_bp", 120.0)),
        "diastolic_bp": float(vitals.get("diastolic_bp", 80.0)),
        "temperature": float(vitals.get("temperature", 37.0)),
        "respiratory_rate": float(vitals.get("respiratory_rate", 16.0)),
        **physio,
        **temporal,
    }
    return features
