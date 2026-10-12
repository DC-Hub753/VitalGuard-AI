"""Documented alert generation rules for clinical, ML, trend, and data quality triggers."""
from __future__ import annotations

from typing import Any
from .alert_service import create_or_deduplicate_alert


def evaluate_and_generate_alerts(
    patient_id: str,
    assessment: dict[str, Any],
    source_event_id: str | int | None = None,
) -> list[dict[str, Any]]:
    """Generate categorized, deduplicated alerts from an assessment payload.

    Separates:
    - clinical_rule (NEWS2)
    - ml_derived (XGBoost 6h horizon)
    - trend_warning (validated hemodynamics trends)
    - data_quality (plausibility & missing data)
    """
    generated_alerts: list[dict[str, Any]] = []
    base_key = f"pt:{patient_id}:evt:{source_event_id or 'latest'}"

    # 1. Clinical Rule Alerts (NEWS2)
    news2 = assessment.get("news2", {})
    total_score = news2.get("total_score")
    is_extreme_single = news2.get("single_parameter_extreme", False)

    if total_score is not None:
        if total_score >= 7:
            alert = create_or_deduplicate_alert(
                patient_id=patient_id,
                event_key=f"{base_key}:news2:critical",
                severity="critical",
                title=f"Critical NEWS2 Escalation (Score {total_score})",
                alert_type="clinical_rule",
                details={
                    "total_score": total_score,
                    "risk_level": "High",
                    "escalation_response": news2.get("escalation_response"),
                    "parameter_scores": news2.get("parameter_scores"),
                },
            )
            if alert:
                generated_alerts.append(alert)
        elif total_score >= 5 or is_extreme_single:
            alert = create_or_deduplicate_alert(
                patient_id=patient_id,
                event_key=f"{base_key}:news2:high",
                severity="high",
                title=f"Elevated NEWS2 Alert (Score {total_score})",
                alert_type="clinical_rule",
                details={
                    "total_score": total_score,
                    "single_parameter_extreme": is_extreme_single,
                    "escalation_response": news2.get("escalation_response"),
                },
            )
            if alert:
                generated_alerts.append(alert)

    # 2. ML-Derived Risk Alerts (XGBoost 6h Horizon)
    ml = assessment.get("ml_prediction", {})
    ml_prob = ml.get("probability")
    if ml_prob is not None:
        if ml_prob >= 0.80:
            alert = create_or_deduplicate_alert(
                patient_id=patient_id,
                event_key=f"{base_key}:ml:critical",
                severity="critical",
                title=f"Critical ML Deterioration Risk ({round(ml_prob * 100)}%)",
                alert_type="ml_derived",
                details={
                    "probability": ml_prob,
                    "prediction_horizon": ml.get("prediction_horizon"),
                    "model_version": ml.get("model_version"),
                },
            )
            if alert:
                generated_alerts.append(alert)
        elif ml_prob >= 0.60:
            alert = create_or_deduplicate_alert(
                patient_id=patient_id,
                event_key=f"{base_key}:ml:high",
                severity="high",
                title=f"High ML Deterioration Risk ({round(ml_prob * 100)}%)",
                alert_type="ml_derived",
                details={
                    "probability": ml_prob,
                    "prediction_horizon": ml.get("prediction_horizon"),
                    "model_version": ml.get("model_version"),
                },
            )
            if alert:
                generated_alerts.append(alert)

    # 3. Trend-Aware Warnings
    derived = assessment.get("derived_features", {})
    spo2_trend = derived.get("spo2_trend_30m", 0.0)
    hr_trend = derived.get("hr_trend_30m", 0.0)
    sys_trend = derived.get("sys_trend_30m", 0.0)
    shock_index = derived.get("shock_index", 0.0)

    # Detect rapid deterioration: SpO2 drop >= 4% or HR rise >= 25 bpm or Shock Index > 0.9
    trend_reasons = []
    if spo2_trend <= -4.0:
        trend_reasons.append(f"SpO2 decreased by {abs(spo2_trend)}% over window")
    if hr_trend >= 25.0:
        trend_reasons.append(f"Heart rate increased by {hr_trend} bpm over window")
    if sys_trend <= -20.0:
        trend_reasons.append(f"Systolic BP dropped by {abs(sys_trend)} mmHg over window")
    if shock_index >= 0.95:
        trend_reasons.append(f"Elevated shock index ({shock_index})")

    if trend_reasons:
        alert = create_or_deduplicate_alert(
            patient_id=patient_id,
            event_key=f"{base_key}:trend:warning",
            severity="high",
            title="Rapid Hemodynamic Deterioration Trend",
            alert_type="trend_warning",
            details={
                "reasons": trend_reasons,
                "derived_features": derived,
            },
        )
        if alert:
            generated_alerts.append(alert)

    # 4. Data Quality or Missing Data Warnings
    quality = assessment.get("data_quality", {})
    if quality and not quality.get("is_plausible", True):
        alert = create_or_deduplicate_alert(
            patient_id=patient_id,
            event_key=f"{base_key}:quality:warning",
            severity="medium",
            title="Sensor Data Quality Warning",
            alert_type="data_quality",
            details={
                "warnings": quality.get("warnings", []),
                "quality_score": quality.get("quality_score"),
            },
        )
        if alert:
            generated_alerts.append(alert)

    return generated_alerts
