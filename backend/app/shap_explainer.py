"""TreeSHAP local feature attribution explainer for the XGBoost pipeline.

Computes exact additive TreeSHAP explanations from the deployed model.
Strictly distinguishes model mathematical attributions from clinical guidelines.
"""
from __future__ import annotations

import logging
from typing import Any
import numpy as np
import shap

from .xgboost_pipeline import FEATURE_NAMES, MODEL_VERSION, xgb_pipeline

logger = logging.getLogger(__name__)


class ShapExplainerService:
    """Manages TreeSHAP explanations for the XGBoost model."""

    def __init__(self) -> None:
        self.explainer: shap.TreeExplainer | None = None
        self._init_explainer()

    def _init_explainer(self) -> None:
        try:
            if xgb_pipeline.model is not None:
                self.explainer = shap.TreeExplainer(xgb_pipeline.model)
                logger.info("TreeExplainer successfully initialized.")
        except Exception as exc:
            logger.warning(f"Could not initialize TreeExplainer: {exc}")
            self.explainer = None

    def explain(self, feature_dict: dict[str, float]) -> dict[str, Any]:
        """Compute exact TreeSHAP values for an observation."""
        if self.explainer is None:
            return {
                "available": False,
                "reason": "TreeExplainer is not initialized",
                "contributions": [],
                "base_value": 0.0,
            }

        vector = np.array([[feature_dict[fn] for fn in FEATURE_NAMES]], dtype=float)
        try:
            shap_values = self.explainer.shap_values(vector)
            base_val = float(self.explainer.expected_value) if hasattr(self.explainer, "expected_value") else 0.0
            if isinstance(base_val, (list, np.ndarray)):
                base_val = float(base_val[0])

            # 1D array of values for the single sample
            vals = shap_values[0] if isinstance(shap_values, (list, np.ndarray)) and len(shap_values.shape) > 1 else shap_values

            total_abs = float(np.sum(np.abs(vals))) or 1.0

            contributions = []
            for i, fn in enumerate(FEATURE_NAMES):
                sv = float(vals[i])
                contributions.append({
                    "feature": fn,
                    "observed_value": round(float(vector[0, i]), 2),
                    "shap_value": round(sv, 4),
                    "direction": "increases-risk" if sv > 0 else "decreases-risk",
                    "relative_importance_pct": round((abs(sv) / total_abs) * 100, 1),
                })

            # Sort by absolute SHAP impact
            contributions.sort(key=lambda item: abs(item["shap_value"]), reverse=True)

            return {
                "available": True,
                "model_version": MODEL_VERSION,
                "method": "TreeSHAP (exact tree attribution)",
                "base_value": round(base_val, 4),
                "top_risk_drivers": contributions[:5],
                "all_contributions": contributions,
                "caveat": (
                    "TreeSHAP values indicate mathematical feature attributions to the XGBoost score. "
                    "They do not establish clinical causation and must not replace professional clinical judgement."
                ),
            }
        except Exception as exc:
            logger.error(f"Error computing TreeSHAP: {exc}")
            return {
                "available": False,
                "reason": str(exc),
                "contributions": [],
                "base_value": 0.0,
            }


# Global singleton explainer
shap_service = ShapExplainerService()
