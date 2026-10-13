"""Regression tests for ingestion input integrity."""
import math

import pytest
from pydantic import ValidationError

from app.observation_contract import VitalsMeasurements


@pytest.mark.parametrize("field", [
    "heart_rate",
    "spo2",
    "systolic_bp",
    "diastolic_bp",
    "temperature",
    "respiratory_rate",
])
@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_vitals_reject_non_finite_measurements(field, bad_value):
    values = {
        "heart_rate": 78.0,
        "spo2": 98.0,
        "systolic_bp": 120.0,
        "diastolic_bp": 80.0,
        "temperature": 36.8,
        "respiratory_rate": 16.0,
        "age": 55,
    }
    values[field] = bad_value

    with pytest.raises(ValidationError):
        VitalsMeasurements.model_validate(values)


def test_vitals_still_accept_finite_measurements():
    values = {
        "heart_rate": 78.0,
        "spo2": 98.0,
        "systolic_bp": 120.0,
        "diastolic_bp": 80.0,
        "temperature": 36.8,
        "respiratory_rate": 16.0,
        "age": 55,
    }
    result = VitalsMeasurements.model_validate(values)
    assert result.heart_rate == 78.0
