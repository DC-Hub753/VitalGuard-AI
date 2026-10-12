"""Comprehensive clinical risk assessment service uniting NEWS2, XGBoost, and TreeSHAP.

Strictly preserves separation of concerns:
- Deterministic clinical rule scores (NEWS2) are computed independently.
- Statistical ML predictions (XGBoost 6h horizon) are clearly attributed.
- TreeSHAP explanations originate from the deployed XGBoost model.
- Incompatible scores are NEVER combined into an arbitrary merged percentage.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .news2 import score_news2
from .observation_contract import evaluate_vitals_quality, VitalsMeasurements
from .shap_explainer import shap_service
from .temporal_features import build_full_feature_vector
from .xgboost_pipeline import xgb_pipeline


def compute_comprehensive_assessment(
    patient_id: str,
    vitals: dict[str, Any],
    prior_observations: list[dict[str, Any]] | None = None,
    spo2_scale: int = 1,
    supplemental_oxygen: bool = False,
    consciousness: str = "alert",
) -> dict[str, Any]:
    """Assemble authoritative NEWS2 score, XGBoost prediction, and TreeSHAP attribution."""
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Authoritative NEWS2 Scoring
    news2_input = {
        "respiratory_rate": vitals.get("respiratory_rate"),
        "spo2": vitals.get("spo2"),
        "systolic_bp": vitals.get("systolic_bp"),
        "heart_rate": vitals.get("heart_rate"),
        "temperature": vitals.get("temperature"),
        "consciousness": vitals.get("consciousness", consciousness),
        "supplemental_oxygen": vitals.get("supplemental_oxygen", supplemental_oxygen),
        "spo2_scale": vitals.get("spo2_scale", spo2_scale),
    }
    news2_result = score_news2(news2_input)

    # 2. Physiological Plausibility Assessment
    quality_result = None
    try:
        measurements = VitalsMeasurements(
            heart_rate=float(vitals.get("heart_rate", 80)),
            spo2=float(vitals.get("spo2", 98)),
            systolic_bp=float(vitals.get("systolic_bp", 120)),
            diastolic_bp=float(vitals.get("diastolic_bp", 80)),
            temperature=float(vitals.get("temperature", 37)),
            respiratory_rate=float(vitals.get("respiratory_rate", 16)),
            age=int(vitals.get("age", 55)),
        )
        quality_eval = evaluate_vitals_quality(measurements)
        quality_result = {
            "is_plausible": quality_eval.is_plausible,
            "is_abnormal": quality_eval.is_abnormal,
            "quality_score": quality_eval.quality_score,
            "warnings": quality_eval.warnings,
        }
    except Exception as exc:
        quality_result = {
            "is_plausible": False,
            "is_abnormal": True,
            "quality_score": 0.0,
            "warnings": [f"Input validation error: {exc}"],
        }

    # 3. Temporal & Hemodynamic Feature Derivation
    feature_dict = build_full_feature_vector(vitals, prior_observations)

    # 4. XGBoost Prediction (6-hour clinical deterioration horizon)
    ml_prediction = xgb_pipeline.predict(feature_dict)

    # 5. TreeSHAP Local Feature Attribution
    shap_explanation = shap_service.explain(feature_dict)

    return {
        "assessment_timestamp": now_iso,
        "patient_id": patient_id,
        "news2": news2_result,
        "ml_prediction": ml_prediction,
        "shap_explanation": shap_explanation,
        "derived_features": {
            "shock_index": feature_dict["shock_index"],
            "pulse_pressure": feature_dict["pulse_pressure"],
            "mean_arterial_pressure": feature_dict["mean_arterial_pressure"],
            "hr_trend_30m": feature_dict["hr_trend_30m"],
            "spo2_trend_30m": feature_dict["spo2_trend_30m"],
            "rr_trend_30m": feature_dict["rr_trend_30m"],
            "sys_trend_30m": feature_dict["sys_trend_30m"],
        },
        "data_quality": quality_result,
        "provenance": {
            "demo_only": True,
            "clinically_validated": False,
            "separation_of_concerns_policy": (
                "NEWS2 clinical guidance and XGBoost ML probabilities are reported separately. "
                "Incompatible clinical scores are never blended into arbitrary merged risk percentages."
            ),
        },
    }
