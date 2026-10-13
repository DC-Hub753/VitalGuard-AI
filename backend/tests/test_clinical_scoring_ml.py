"""Phase 4 test suite: Authoritative NEWS2 scoring, reproducible XGBoost pipeline, and TreeSHAP."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.news2 import score_news2
from app.risk_assessment_service import compute_comprehensive_assessment
from app.shap_explainer import shap_service
from app.temporal_features import build_full_feature_vector, derive_physiological_features
from app.xgboost_pipeline import (
    FEATURE_NAMES,
    MODEL_VERSION,
    PREDICTION_HORIZON,
    generate_patient_episodes,
    xgb_pipeline,
)
from auth_helpers import authenticate_test_client


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VITALGUARD_DB_PATH", str(tmp_path / "clinical_ml.sqlite3"))
    with TestClient(app) as test_client:
        authenticate_test_client(test_client)
        yield test_client


# ==============================================================================
# 1. Authoritative NEWS2 Scoring Tests
# ==============================================================================

def test_news2_missing_measurements_are_not_treated_as_normal():
    # Only respiratory rate provided, other vitals missing
    incomplete = {"respiratory_rate": 16}
    result = score_news2(incomplete)

    assert result["is_complete"] is False
    assert "spo2" in result["missing_parameters"]
    assert "systolic_bp" in result["missing_parameters"]
    assert "heart_rate" in result["missing_parameters"]
    assert "temperature" in result["missing_parameters"]
    assert result["parameter_scores"]["spo2"] is None
    assert result["total_score"] is None  # incomplete panel must not expose a total
    assert result["partial_score"] == 0
    assert result["clinical_risk_level"] == "Incomplete (Undetermined)"


def test_news2_single_parameter_extreme_triggers_urgent_nurse_review():
    # Respiratory rate is 26 (scores 3), but all other vitals are normal
    values = {
        "respiratory_rate": 26,
        "spo2": 98,
        "systolic_bp": 120,
        "heart_rate": 75,
        "temperature": 37.0,
        "consciousness": "alert",
        "supplemental_oxygen": False,
        "spo2_scale": 1,
    }
    result = score_news2(values)

    assert result["is_complete"] is True
    assert result["total_score"] == 3
    assert result["single_parameter_extreme"] is True
    assert result["clinical_risk_level"] == "Low-Medium (Single Parameter Extreme)"
    assert "Urgent review by registered nurse" in result["escalation_response"]


def test_news2_high_risk_escalation_threshold():
    # Multiple abnormal vitals: RR=26 (3), SpO2=90 (3), HR=135 (3) -> total 9
    values = {
        "respiratory_rate": 26,
        "spo2": 90,
        "systolic_bp": 120,
        "heart_rate": 135,
        "temperature": 37.0,
        "consciousness": "alert",
        "supplemental_oxygen": False,
        "spo2_scale": 1,
    }
    result = score_news2(values)

    assert result["total_score"] == 9
    assert result["clinical_risk_level"] == "High"
    assert "Emergency assessment" in result["escalation_response"]
    assert "Continuous" in result["monitoring_frequency"]


def test_news2_incomplete_data_still_triggers_escalation_if_extreme_observed():
    # Missing blood pressure and temperature, but RR=28 (scores 3)
    incomplete_extreme = {
        "respiratory_rate": 28,
        "spo2": 97,
        "heart_rate": 80,
    }
    result = score_news2(incomplete_extreme)

    assert result["is_complete"] is False
    assert result["single_parameter_extreme"] is True
    # Must flag low_medium even with incomplete data
    assert result["clinical_risk_level"] == "Low-Medium (Single Parameter Extreme)"


# ==============================================================================
# 2. XGBoost Training & Zero Patient-Leakage Tests
# ==============================================================================

def test_xgboost_training_avoids_patient_leakage():
    X, y, groups = generate_patient_episodes(seed=20261010, num_patients=200)
    assert len(X) == len(groups)

    # Verify pipeline metrics recorded zero patient leakage
    metrics = xgb_pipeline.evaluation_metrics
    assert metrics["patient_leakage_check"] == "passed_zero_overlap"
    assert metrics["train_patients"] > 0
    assert metrics["test_patients"] > 0
    assert metrics["metrics"]["auroc"] >= 0.70  # Valid discriminative capability


def test_xgboost_prediction_horizon_and_version():
    assert xgb_pipeline.model is not None
    vitals = {
        "age": 65,
        "heart_rate": 110,
        "spo2": 92,
        "systolic_bp": 95,
        "diastolic_bp": 60,
        "temperature": 38.5,
        "respiratory_rate": 24,
    }
    features = build_full_feature_vector(vitals)
    prediction = xgb_pipeline.predict(features)

    assert prediction["model_version"] == MODEL_VERSION
    assert prediction["prediction_horizon"] == PREDICTION_HORIZON
    assert 0.0 <= prediction["probability"] <= 1.0
    assert prediction["risk_score"] in range(0, 101)


# ==============================================================================
# 3. Temporal Features & Physiological Ratios Tests
# ==============================================================================

def test_physiological_features_derivation():
    vitals = {"heart_rate": 100.0, "systolic_bp": 100.0, "diastolic_bp": 70.0}
    physio = derive_physiological_features(vitals)

    # Shock index: 100 / 100 = 1.0
    assert physio["shock_index"] == 1.0
    # Pulse pressure: 100 - 70 = 30
    assert physio["pulse_pressure"] == 30.0
    # MAP: 70 + (30 / 3) = 80.0
    assert physio["mean_arterial_pressure"] == 80.0


def test_feature_vector_contains_all_model_features():
    vitals = {
        "age": 58,
        "heart_rate": 84,
        "spo2": 98,
        "systolic_bp": 120,
        "diastolic_bp": 80,
        "temperature": 37.0,
        "respiratory_rate": 16,
    }
    feats = build_full_feature_vector(vitals)
    for fn in FEATURE_NAMES:
        assert fn in feats


# ==============================================================================
# 4. TreeSHAP Explainability Tests
# ==============================================================================

def test_shap_explanation_originates_from_deployed_model():
    vitals = {
        "age": 72,
        "heart_rate": 125,
        "spo2": 89,
        "systolic_bp": 88,
        "diastolic_bp": 55,
        "temperature": 39.2,
        "respiratory_rate": 28,
    }
    features = build_full_feature_vector(vitals)
    explanation = shap_service.explain(features)

    assert explanation["available"] is True
    assert explanation["method"] == "TreeSHAP (exact tree attribution)"
    assert len(explanation["top_risk_drivers"]) == 5
    assert len(explanation["all_contributions"]) == len(FEATURE_NAMES)

    top_feature = explanation["top_risk_drivers"][0]
    assert "feature" in top_feature
    assert "shap_value" in top_feature
    assert "direction" in top_feature
    assert top_feature["direction"] in ("increases-risk", "decreases-risk")


# ==============================================================================
# 5. Integrated Risk Assessment Contract (Separation of Concerns)
# ==============================================================================

def test_comprehensive_assessment_preserves_separation_of_concerns():
    vitals = {
        "age": 68,
        "heart_rate": 115,
        "spo2": 93,
        "systolic_bp": 98,
        "diastolic_bp": 62,
        "temperature": 38.6,
        "respiratory_rate": 22,
    }
    assessment = compute_comprehensive_assessment("DEMO-SEP-001", vitals)

    # NEWS2 component
    assert "news2" in assessment
    assert assessment["news2"]["score_name"] == "NEWS2"
    assert "clinical_risk_level" in assessment["news2"]

    # ML component
    assert "ml_prediction" in assessment
    assert assessment["ml_prediction"]["prediction_horizon"] == PREDICTION_HORIZON
    assert assessment["ml_prediction"]["model_version"] == MODEL_VERSION

    # TreeSHAP component
    assert "shap_explanation" in assessment
    assert assessment["shap_explanation"]["available"] is True

    # Provenance and unblended separation statement
    assert "separation_of_concerns_policy" in assessment["provenance"]
    assert "never blended" in assessment["provenance"]["separation_of_concerns_policy"]


def test_api_comprehensive_assessment_endpoint(client):
    payload = {
        "patient_id": "DEMO-API-001",
        "age": 60,
        "heart_rate": 88,
        "spo2": 97,
        "systolic_bp": 124,
        "diastolic_bp": 82,
        "temperature": 37.1,
        "respiratory_rate": 16,
    }
    res = client.post("/api/v1/risk/assessment", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["patient_id"] == "DEMO-API-001"
    assert "news2" in data
    assert "ml_prediction" in data
    assert "shap_explanation" in data
    assert "derived_features" in data
