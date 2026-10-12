"""Patient prioritization engine sorting and filtering by real-time risk, trends, ward, and freshness."""
from __future__ import annotations

import json
from typing import Any, Literal
from sqlalchemy import desc, select

from .alert_service import list_alerts
from .ingestion_store import get_patient_freshness
from .patient_service import list_patients
from .storage import _OBSERVATIONS, _engine
from .storage_schema import alerts, patients

RiskCategory = Literal["critical", "high", "medium", "low", "needs_review"]


def prioritize_patients(
    *,
    ward: str | None = None,
    risk_category: str | None = None,
    has_open_alerts: bool | None = None,
    stale_only: bool = False,
    sort_by: Literal["priority", "news2_desc", "ml_desc", "patient_id"] = "priority",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Calculate dynamic clinical priority rankings across admitted patients."""
    engine = _engine()
    all_patients, total_patients = list_patients(active_only=True, ward=ward, limit=200)

    prioritized_list = []

    with engine.connect() as connection:
        for p in all_patients:
            pid = p["patient_id"]

            # 1. Fetch latest observation
            latest_obs = connection.execute(
                select(_OBSERVATIONS)
                .where(_OBSERVATIONS.c.patient_id == pid)
                .order_by(desc(_OBSERVATIONS.c.id))
                .limit(1)
            ).mappings().first()

            # 2. Check open / unreviewed alerts
            open_alerts = connection.execute(
                select(alerts)
                .where(
                    alerts.c.patient_id == pid,
                    alerts.c.status.in_(["open", "reopened"]),
                )
            ).mappings().all()

            open_count = len(open_alerts)
            highest_severity = None
            if open_alerts:
                severities = {a["severity"] for a in open_alerts}
                if "critical" in severities:
                    highest_severity = "critical"
                elif "high" in severities:
                    highest_severity = "high"
                elif "medium" in severities:
                    highest_severity = "medium"
                else:
                    highest_severity = "low"

            # 3. Check data freshness
            freshness = get_patient_freshness(pid, stale_threshold_seconds=300)
            is_stale = freshness.get("freshness") == "stale" or not freshness.get("has_data")

            # 4. Extract risk scores
            news2_score = None
            ml_prob = None
            risk_cat: RiskCategory = "low"
            needs_review = False
            review_reason = []

            if latest_obs:
                pred_json = json.loads(latest_obs["prediction_json"]) if latest_obs["prediction_json"] else {}
                news2_score = pred_json.get("news2_total") or pred_json.get("news2_score")
                ml_prob = pred_json.get("model_probability")
            else:
                needs_review = True
                review_reason.append("No baseline observation recorded")

            if is_stale:
                needs_review = True
                review_reason.append("Patient data is stale or disconnected")

            # Determine Priority Rank & Category
            # Rank 1: Critical, Rank 2: High, Rank 3: Medium, Rank 4: Needs Review (stale/missing), Rank 5: Low
            priority_rank = 5
            if highest_severity == "critical" or (news2_score and news2_score >= 7) or (ml_prob and ml_prob >= 0.80):
                priority_rank = 1
                risk_cat = "critical"
            elif highest_severity == "high" or (news2_score and news2_score >= 5) or (ml_prob and ml_prob >= 0.60):
                priority_rank = 2
                risk_cat = "high"
            elif highest_severity == "medium" or (news2_score and news2_score >= 3):
                priority_rank = 3
                risk_cat = "medium"
            elif needs_review:
                priority_rank = 4
                risk_cat = "needs_review"
            else:
                priority_rank = 5
                risk_cat = "low"

            item = {
                "patient_id": pid,
                "display_name": p["display_name"],
                "ward": p["ward"],
                "bed": p["bed"],
                "priority_rank": priority_rank,
                "risk_category": risk_cat,
                "needs_review": needs_review,
                "review_reasons": review_reason,
                "news2_score": news2_score,
                "ml_probability": ml_prob,
                "open_alerts_count": open_count,
                "highest_alert_severity": highest_severity,
                "freshness_status": freshness.get("freshness", "stale"),
                "latest_observed_at": freshness.get("latest_observed_at"),
            }
            prioritized_list.append(item)

    # Filtering
    filtered = prioritized_list
    if risk_category:
        filtered = [it for it in filtered if it["risk_category"] == risk_category]
    if has_open_alerts is not None:
        filtered = [it for it in filtered if (it["open_alerts_count"] > 0) == has_open_alerts]
    if stale_only:
        filtered = [it for it in filtered if it["freshness_status"] == "stale"]

    # Sorting
    if sort_by == "priority":
        filtered.sort(key=lambda it: (it["priority_rank"], -(it["news2_score"] or 0), -(it["ml_probability"] or 0)))
    elif sort_by == "news2_desc":
        filtered.sort(key=lambda it: -(it["news2_score"] or -1))
    elif sort_by == "ml_desc":
        filtered.sort(key=lambda it: -(it["ml_probability"] or -1))
    elif sort_by == "patient_id":
        filtered.sort(key=lambda it: it["patient_id"])

    total_matching = len(filtered)
    paged = filtered[offset : offset + limit]

    return {
        "items": paged,
        "total": total_matching,
        "count": len(paged),
        "limit": limit,
        "offset": offset,
        "ward_filter": ward,
        "risk_filter": risk_category,
        "demo_only": True,
    }
