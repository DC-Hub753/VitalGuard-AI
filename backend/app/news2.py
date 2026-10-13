"""Authoritative NEWS2 (National Early Warning Score 2) scoring engine.

Based on the Royal College of Physicians (RCP) NEWS2 specification (2017).
Maintains strict separation between deterministic clinical scoring rules
and statistical machine learning predictions.

Reference:
Royal College of Physicians. National Early Warning Score (NEWS) 2:
Standardising the assessment of acute-illness severity in the NHS.
Updated report of a working party. London: RCP, 2017.
"""
from __future__ import annotations

from typing import Any


RCP_CLINICAL_RISK = {
    "normal": {
        "level": "Normal",
        "monitoring_frequency": "Minimum 12-hourly monitoring or routine clinical care",
        "escalation_response": "Continue routine clinical monitoring on ward.",
    },
    "low": {
        "level": "Low",
        "monitoring_frequency": "Minimum 4–6 hourly monitoring",
        "escalation_response": "Informed registered nurse decides whether increased frequency or escalation is needed.",
    },
    "low_medium": {
        "level": "Low-Medium (Single Parameter Extreme)",
        "monitoring_frequency": "Minimum 4-hourly monitoring",
        "escalation_response": "Urgent review by registered nurse; decide whether escalation to medical team is warranted.",
    },
    "medium": {
        "level": "Medium",
        "monitoring_frequency": "Minimum 1-hourly monitoring",
        "escalation_response": "Urgent review by ward doctor or acute care team to determine clinical management.",
    },
    "high": {
        "level": "High",
        "monitoring_frequency": "Continuous vital-signs monitoring",
        "escalation_response": "Emergency assessment by clinical team with critical care competencies / Outreach / ICU.",
    },
    "incomplete_undetermined": {
        "level": "Incomplete (Undetermined)",
        "monitoring_frequency": "Obtain missing vital sign measurements immediately",
        "escalation_response": "Complete vital sign panel required before authoritative NEWS2 risk determination.",
    },
}


def score_respiratory_rate(rr: float | int | None) -> int | None:
    if rr is None:
        return None
    val = float(rr)
    if val <= 8 or val >= 25:
        return 3
    if 9 <= val <= 11:
        return 1
    if 21 <= val <= 24:
        return 2
    return 0


def score_spo2(spo2: float | int | None, scale: int = 1, supplemental_oxygen: bool = False) -> int | None:
    if spo2 is None:
        return None
    val = float(spo2)
    if scale == 1:
        # Scale 1: Target 96-100%
        if val <= 91:
            return 3
        if val <= 93:
            return 2
        if val <= 95:
            return 1
        return 0
    else:
        # Scale 2: Prescribed target 88-92% (hypercapnic respiratory failure)
        if supplemental_oxygen:
            if val <= 83 or val >= 97:
                return 3
            if val <= 85 or val >= 95:
                return 2
            if val <= 87 or val >= 93:
                return 1
            return 0
        else:
            if val <= 83:
                return 3
            if val <= 85:
                return 2
            if val <= 87:
                return 1
            return 0


def score_systolic_bp(sys: float | int | None) -> int | None:
    if sys is None:
        return None
    val = float(sys)
    if val <= 90 or val >= 220:
        return 3
    if val <= 100:
        return 2
    if val <= 110:
        return 1
    return 0


def score_heart_rate(hr: float | int | None) -> int | None:
    if hr is None:
        return None
    val = float(hr)
    if val <= 40 or val >= 131:
        return 3
    if val <= 50 or (91 <= val <= 110):
        return 1
    if 111 <= val <= 130:
        return 2
    return 0


def score_consciousness(consciousness: str | None) -> int | None:
    if consciousness is None:
        return None
    norm = str(consciousness).strip().lower()
    if norm in ("alert", "a"):
        return 0
    # Voice (V), Pain (P), Unresponsive (U), or New Confusion (C)
    if norm in ("voice", "v", "pain", "p", "unresponsive", "u", "new_confusion", "confusion", "c"):
        return 3
    return None


def score_temperature(temp: float | int | None) -> int | None:
    if temp is None:
        return None
    val = float(temp)
    if val <= 35.0:
        return 3
    if val <= 36.0:
        return 1
    if val <= 38.0:
        return 0
    if val <= 39.0:
        return 1
    return 2


def score_supplemental_oxygen(oxygen: bool | None) -> int | None:
    if oxygen is None:
        return None
    return 2 if bool(oxygen) else 0


def score_news2(values: dict[str, Any]) -> dict[str, Any]:
    """Score vital signs according to the RCP NEWS2 specification.

    Handles complete panels and explicit missing inputs without treating missing values as normal.
    """
    scale = int(values.get("spo2_scale", 1))
    if scale not in (1, 2):
        raise ValueError("spo2_scale must be 1 or 2")
    oxygen = values.get("supplemental_oxygen")

    rr = values.get("respiratory_rate")
    spo2 = values.get("spo2")
    systolic = values.get("systolic_bp")
    hr = values.get("heart_rate")
    temp = values.get("temperature")
    consciousness = values.get("consciousness")

    param_scores: dict[str, int | None] = {
        "respiratory_rate": score_respiratory_rate(rr),
        "spo2": score_spo2(spo2, scale=scale, supplemental_oxygen=bool(oxygen) if oxygen is not None else False),
        "supplemental_oxygen": score_supplemental_oxygen(oxygen),
        "systolic_bp": score_systolic_bp(systolic),
        "heart_rate": score_heart_rate(hr),
        "consciousness": score_consciousness(consciousness),
        "temperature": score_temperature(temp),
    }

    missing = [k for k, v in param_scores.items() if v is None]
    is_complete = len(missing) == 0

    available_scores = [v for v in param_scores.values() if v is not None]
    partial_score = sum(available_scores)
    total_score = partial_score if is_complete else None

    # Individual parameter extreme check (Score of 3 in any single parameter triggers clinical review)
    single_parameter_extreme = any(v == 3 for v in available_scores)

    # Risk band determination
    if is_complete and total_score is not None:
        if total_score == 0:
            risk_key = "normal"
        elif total_score >= 7:
            risk_key = "high"
        elif total_score >= 5:
            risk_key = "medium"
        elif single_parameter_extreme:
            risk_key = "low_medium"
        else:
            risk_key = "low"
    else:
        # Incomplete data handling
        if partial_score >= 7:
            risk_key = "high"
        elif partial_score >= 5:
            risk_key = "medium"
        elif single_parameter_extreme:
            risk_key = "low_medium"
        else:
            risk_key = "incomplete_undetermined"

    risk_info = RCP_CLINICAL_RISK[risk_key]

    return {
        "score_name": "NEWS2",
        "score_version": "Royal College of Physicians NEWS2 (2017)",
        "parameter_scores": param_scores,
        "total_score": total_score,
        "is_complete": is_complete,
        "missing_parameters": missing,
        "partial_score": partial_score,
        "single_parameter_extreme": single_parameter_extreme,
        "clinical_risk_level": risk_info["level"],
        "monitoring_frequency": risk_info["monitoring_frequency"],
        "escalation_response": risk_info["escalation_response"],
        "spo2_scale": scale,
        "supplemental_oxygen": bool(oxygen) if oxygen is not None else False,
        "demo_only": True,
        "clinically_validated_implementation": False,
        "disclaimer": (
            "Software demonstration only. Verify any clinical scoring against the official RCP chart "
            "and local hospital policy. Not for diagnosis, triage, escalation, or treatment decisions."
        ),
    }
