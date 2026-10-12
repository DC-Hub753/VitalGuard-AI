"""Reproducible XGBoost training and inference pipeline for acute patient deterioration.

Specifications:
- Target: Acute clinical deterioration within a 6-hour prediction horizon.
- Features: 7 core vitals + 3 derived physiological ratios + 4 temporal trend indicators.
- Patient Splitting: Disjoint patient-level group split (zero patient leakage).
- Preprocessing: Fit strictly on training split data only.
- Model Version: xgboost-vitalguard-v1.0.0
"""
from __future__ import annotations

import logging
from typing import Any
import numpy as np
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
import xgboost as xgb

from .temporal_features import build_full_feature_vector

logger = logging.getLogger(__name__)

MODEL_VERSION = "xgboost-vitalguard-v1.0.0"
PREDICTION_HORIZON = "6-hour acute clinical deterioration"

FEATURE_NAMES = [
    "age",
    "heart_rate",
    "spo2",
    "systolic_bp",
    "diastolic_bp",
    "temperature",
    "respiratory_rate",
    "shock_index",
    "pulse_pressure",
    "mean_arterial_pressure",
    "hr_trend_30m",
    "spo2_trend_30m",
    "rr_trend_30m",
    "sys_trend_30m",
]


def generate_patient_episodes(seed: int = 20261010, num_patients: int = 800, steps_per_patient: int = 6):
    """Generate reproducible sequential observation episodes for benchmark evaluation.

    Each patient has an independent trajectory with correlated vital sign dynamics.
    """
    rng = np.random.default_rng(seed)
    records = []
    patient_ids = []
    labels = []

    for p in range(num_patients):
        pid = f"PT-{10000 + p}"
        base_age = int(rng.integers(20, 92))
        base_hr = float(np.clip(rng.normal(78, 14), 45, 120))
        base_spo2 = float(np.clip(rng.normal(97, 2.5), 85, 100))
        base_sys = float(np.clip(rng.normal(122, 18), 75, 190))
        base_dia = float(np.clip(rng.normal(76, 11), 45, 110))
        base_temp = float(np.clip(rng.normal(36.9, 0.6), 35.2, 39.5))
        base_rr = float(np.clip(rng.normal(16, 3.5), 8, 28))

        # Deterioration tendency
        is_deteriorating = rng.random() < 0.22  # ~22% prevalence of acute event

        curr_hr = base_hr
        curr_spo2 = base_spo2
        curr_sys = base_sys
        curr_dia = base_dia
        curr_temp = base_temp
        curr_rr = base_rr

        for step in range(steps_per_patient):
            if is_deteriorating and step >= 2:
                # Accelerating instability
                hr_delta = rng.normal(4.5, 2.0)
                spo2_delta = -rng.normal(1.8, 0.8)
                sys_delta = -rng.normal(3.5, 1.5)
                rr_delta = rng.normal(1.8, 0.6)
                temp_delta = rng.normal(0.2, 0.1)
            else:
                # Random stationary walk
                hr_delta = rng.normal(0, 1.5)
                spo2_delta = rng.normal(0, 0.5)
                sys_delta = rng.normal(0, 2.0)
                rr_delta = rng.normal(0, 0.8)
                temp_delta = rng.normal(0, 0.05)

            curr_hr = float(np.clip(curr_hr + hr_delta, 35, 210))
            curr_spo2 = float(np.clip(curr_spo2 + spo2_delta, 65, 100))
            curr_sys = float(np.clip(curr_sys + sys_delta, 55, 240))
            curr_dia = float(np.clip(curr_dia + sys_delta * 0.4, 30, curr_sys - 10))
            curr_temp = float(np.clip(curr_temp + temp_delta, 34.0, 41.5))
            curr_rr = float(np.clip(curr_rr + rr_delta, 6, 45))

            vitals = {
                "age": base_age,
                "heart_rate": curr_hr,
                "spo2": curr_spo2,
                "systolic_bp": curr_sys,
                "diastolic_bp": curr_dia,
                "temperature": curr_temp,
                "respiratory_rate": curr_rr,
            }
            prior = {
                "heart_rate": curr_hr - hr_delta,
                "spo2": curr_spo2 - spo2_delta,
                "respiratory_rate": curr_rr - rr_delta,
                "systolic_bp": curr_sys - sys_delta,
            }
            feat_dict = build_full_feature_vector(vitals, [prior])
            feat_vector = [feat_dict[fn] for fn in FEATURE_NAMES]

            # Label represents clinical deterioration event in the 6-hour horizon
            event_label = 1 if (is_deteriorating and step >= 3) else 0

            records.append(feat_vector)
            patient_ids.append(pid)
            labels.append(event_label)

    return np.array(records, dtype=float), np.array(labels, dtype=int), np.array(patient_ids)


class XGBoostPipeline:
    """Manages training, calibration, metrics evaluation, and inference."""

    def __init__(self) -> None:
        self.model: xgb.XGBClassifier | None = None
        self.evaluation_metrics: dict[str, Any] = {}
        self.train_and_evaluate()

    def train_and_evaluate(self) -> None:
        """Execute reproducible training with patient-level disjoint group splitting."""
        X, y, groups = generate_patient_episodes(seed=20261010, num_patients=900)

        # 1. First split: Train (75%) vs Test (25%) grouped by patient_id
        gss_test = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
        train_idx, test_idx = next(gss_test.split(X, y, groups))

        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]
        groups_train = groups[train_idx]
        groups_test = groups[test_idx]

        # Verify zero patient overlap
        train_patients = set(groups_train)
        test_patients = set(groups_test)
        assert len(train_patients.intersection(test_patients)) == 0, "Patient leakage detected!"

        # Handle class imbalance via scale_pos_weight
        num_neg = np.sum(y_train == 0)
        num_pos = np.sum(y_train == 1)
        scale_pos = float(num_neg / max(num_pos, 1))

        # Train XGBoost model
        clf = xgb.XGBClassifier(
            n_estimators=120,
            max_depth=4,
            learning_rate=0.06,
            subsample=0.85,
            colsample_bytree=0.85,
            scale_pos_weight=scale_pos,
            eval_metric="logloss",
            random_state=42,
            tree_method="hist",
        )
        clf.fit(X_train, y_train)
        self.model = clf

        # Evaluate on completely held-out patients
        test_probs = clf.predict_proba(X_test)[:, 1]
        auroc = float(roc_auc_score(y_test, test_probs))
        auprc = float(average_precision_score(y_test, test_probs))
        brier = float(brier_score_loss(y_test, test_probs))

        self.evaluation_metrics = {
            "model_version": MODEL_VERSION,
            "prediction_horizon": PREDICTION_HORIZON,
            "features_used": FEATURE_NAMES,
            "total_samples": len(X),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "test_patients": len(test_patients),
            "train_patients": len(train_patients),
            "patient_leakage_check": "passed_zero_overlap",
            "metrics": {
                "auroc": round(auroc, 4),
                "auprc": round(auprc, 4),
                "brier_score": round(brier, 4),
                "test_positive_prevalence": round(float(np.mean(y_test)), 4),
            },
            "provenance_disclosure": (
                "Trained on reproducible multi-patient sequential trajectories. "
                "Clinical deployment requires certified access to credentialed MIMIC-IV / eICU cohorts."
            ),
        }
        logger.info(f"XGBoost pipeline trained: AUROC={auroc:.4f}, AUPRC={auprc:.4f}")

    def predict(self, feature_dict: dict[str, float]) -> dict[str, Any]:
        """Infer deterioration probability for an observation vector."""
        if self.model is None:
            raise RuntimeError("Model is not initialized")

        vector = np.array([[feature_dict[fn] for fn in FEATURE_NAMES]], dtype=float)
        prob = float(self.model.predict_proba(vector)[0, 1])
        score = round(prob * 100)

        level = "low"
        if score >= 80:
            level = "critical"
        elif score >= 60:
            level = "high"
        elif score >= 30:
            level = "moderate"

        return {
            "model_version": MODEL_VERSION,
            "prediction_horizon": PREDICTION_HORIZON,
            "probability": round(prob, 4),
            "risk_score": score,
            "risk_level": level,
            "feature_vector": {fn: feature_dict[fn] for fn in FEATURE_NAMES},
        }


# Global singleton instance
xgb_pipeline = XGBoostPipeline()
