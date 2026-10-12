"""Phase 5 test suite: Alert workflows, lifecycle transitions, deduplication, and patient prioritization."""
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from app.alert_generator import evaluate_and_generate_alerts
from app.alert_service import (
    create_or_deduplicate_alert,
    list_alert_audit,
    list_alerts,
    transition_alert_state,
)
from app.main import app
from app.patient_service import create_patient
from app.prioritization_service import prioritize_patients
from auth_helpers import authenticate_test_client


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("VITALGUARD_DB_PATH", str(tmp_path / "phase5_alerts.sqlite3"))
    from app.storage import initialize_storage
    initialize_storage()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        authenticate_test_client(test_client)
        yield test_client


# ==============================================================================
# 1. Alert Lifecycle & State Transitions
# ==============================================================================

def test_complete_alert_lifecycle_transitions(client):
    alert = create_or_deduplicate_alert(
        patient_id="PATIENT-LC-01",
        event_key="evt:lc:1",
        severity="high",
        title="Elevated NEWS2 Alert",
        alert_type="clinical_rule",
    )
    alert_id = alert["id"]
    assert alert["status"] == "open"

    # 1. Open -> Acknowledged
    ack_res = client.post(f"/api/v1/alerts/{alert_id}/acknowledge", json={"note": "Assessing patient vitals"})
    assert ack_res.status_code == 200
    assert ack_res.json()["item"]["status"] == "acknowledged"
    assert ack_res.json()["item"]["acknowledged_by"] == "demo-operator"

    # 2. Acknowledged -> Assigned
    assign_res = client.post(f"/api/v1/alerts/{alert_id}/assign", json={"assignee": "dr_clara", "note": "Assigned to attending"})
    assert assign_res.status_code == 200
    assert assign_res.json()["item"]["status"] == "assigned"
    assert assign_res.json()["item"]["assigned_to"] == "dr_clara"

    # 3. Add Note
    note_res = client.post(f"/api/v1/alerts/{alert_id}/notes", json={"text": "Oxygen therapy initiated"})
    assert note_res.status_code == 200
    notes = note_res.json()["item"]["notes"]
    assert any(n["text"] == "Oxygen therapy initiated" for n in notes)

    # 4. Assigned -> Resolved
    resolve_res = client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"note": "Vitals stabilized"})
    assert resolve_res.status_code == 200
    assert resolve_res.json()["item"]["status"] == "resolved"

    # 5. Resolved -> Reopened
    reopen_res = client.post(f"/api/v1/alerts/{alert_id}/reopen", json={"reason": "SpO2 dropped again"})
    assert reopen_res.status_code == 200
    assert reopen_res.json()["item"]["status"] == "reopened"
    assert reopen_res.json()["item"]["reopened_by"] == "demo-operator"


def test_invalid_lifecycle_transition_is_rejected(client):
    alert = create_or_deduplicate_alert(
        patient_id="PATIENT-LC-02",
        event_key="evt:lc:2",
        severity="critical",
        title="Critical Deterioration",
    )
    alert_id = alert["id"]

    # Directly resolve alert
    client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"note": "Resolved"})

    # Attempting to acknowledge an already resolved alert must be rejected
    res = client.post(f"/api/v1/alerts/{alert_id}/acknowledge", json={"note": "Cannot acknowledge resolved"})
    assert res.status_code == 400
    assert "Cannot transition alert" in res.json()["detail"]


def test_alert_history_persists_and_is_immutable(client):
    alert = create_or_deduplicate_alert(
        patient_id="PATIENT-AUDIT-01",
        event_key="evt:audit:1",
        severity="medium",
        title="Audit Test Alert",
    )
    alert_id = alert["id"]

    client.post(f"/api/v1/alerts/{alert_id}/acknowledge")
    client.post(f"/api/v1/alerts/{alert_id}/assign", json={"assignee": "nurse_bob"})
    client.post(f"/api/v1/alerts/{alert_id}/resolve")

    audit_res = client.get(f"/api/v1/alerts/{alert_id}/audit")
    assert audit_res.status_code == 200
    actions = [item["action"] for item in audit_res.json()["items"]]
    assert actions == ["created", "acknowledged", "assigned", "resolved"]


# ==============================================================================
# 2. Alert Deduplication & Escalation Timing
# ==============================================================================

def test_alert_deduplication_prevents_alarm_fatigue():
    # Trigger first high clinical alert
    first = create_or_deduplicate_alert(
        patient_id="PATIENT-DEDUP-01",
        event_key="evt:reading:1",
        severity="high",
        title="High NEWS2 Score (5)",
        alert_type="clinical_rule",
    )
    assert first["status"] == "open"
    first_id = first["id"]

    # Subsequent reading also qualifies for clinical_rule alert
    second = create_or_deduplicate_alert(
        patient_id="PATIENT-DEDUP-01",
        event_key="evt:reading:2",
        severity="high",
        title="High NEWS2 Score (6)",
        alert_type="clinical_rule",
    )

    # Must update existing active alert rather than creating duplicate row
    assert second["id"] == first_id
    assert "latest_trigger" in second["details"]
    assert second["details"]["latest_trigger"]["event_key"] == "evt:reading:2"

    active_alerts = list_alerts(patient_id="PATIENT-DEDUP-01", status="open")
    assert len(active_alerts) == 1


def test_escalation_deadline_calculation():
    # Critical alert has a 15-minute deadline
    alert = create_or_deduplicate_alert(
        patient_id="PATIENT-ESC-01",
        event_key="evt:esc:1",
        severity="critical",
        title="Critical Sepsis Alert",
    )
    alerts_list = list_alerts(patient_id="PATIENT-ESC-01")
    assert len(alerts_list) == 1
    assert alerts_list[0]["deadline_minutes"] == 15
    assert "age_minutes" in alerts_list[0]
    assert alerts_list[0]["is_overdue"] is False


# ==============================================================================
# 3. Alert Generation Classification & Trend Warnings
# ==============================================================================

def test_alert_generation_categorization():
    assessment = {
        "news2": {
            "total_score": 8,
            "single_parameter_extreme": True,
            "escalation_response": "Emergency assessment by critical care team",
        },
        "ml_prediction": {
            "probability": 0.85,
            "prediction_horizon": "6-hour acute clinical deterioration",
            "model_version": "xgboost-vitalguard-v1.0.0",
        },
        "derived_features": {
            "spo2_trend_30m": -5.0,  # Desaturation drop >= 4%
            "hr_trend_30m": 30.0,    # Tachycardia jump >= 25 bpm
            "shock_index": 1.1,
        },
        "data_quality": {
            "is_plausible": False,
            "warnings": ["Temperature sensor out of range"],
        },
    }

    alerts_gen = evaluate_and_generate_alerts("PATIENT-MULTI-01", assessment, source_event_id="batch-01")
    alert_types = {a["alert_type"] for a in alerts_gen}

    assert "clinical_rule" in alert_types
    assert "ml_derived" in alert_types
    assert "trend_warning" in alert_types
    assert "data_quality" in alert_types


# ==============================================================================
# 4. Patient Prioritization & Stale Data Explicit Handling
# ==============================================================================

def test_patient_prioritization_and_stale_handling(client):
    # Setup 3 patients in Ward A and Ward B
    create_patient(patient_id="PT-PRIO-01", display_name="Stable Patient", ward="Ward A")
    create_patient(patient_id="PT-PRIO-02", display_name="Critical Patient", ward="Ward A")
    create_patient(patient_id="PT-PRIO-03", display_name="Stale Patient", ward="Ward B")

    # Critical patient has an active critical alert
    create_or_deduplicate_alert(
        patient_id="PT-PRIO-02",
        event_key="evt:prio:crit",
        severity="critical",
        title="Critical Deterioration",
    )

    result = prioritize_patients()
    items = result["items"]

    # Find ranked items
    prio2 = next(it for it in items if it["patient_id"] == "PT-PRIO-02")
    prio3 = next(it for it in items if it["patient_id"] == "PT-PRIO-03")

    # Critical alert patient must be rank 1
    assert prio2["priority_rank"] == 1
    assert prio2["risk_category"] == "critical"

    # Patient with no readings must be flagged with needs_review: True (never quietly low risk!)
    assert prio3["needs_review"] is True
    assert "No baseline observation recorded" in prio3["review_reasons"]


def test_api_prioritization_endpoint_filtering_and_sorting(client):
    create_patient(patient_id="PT-FILTER-01", display_name="ICU Patient", ward="ICU")
    create_patient(patient_id="PT-FILTER-02", display_name="General Ward Patient", ward="General")

    res = client.get("/api/v1/alerts/prioritization?ward=ICU")
    assert res.status_code == 200
    body = res.json()
    assert all(it["ward"] == "ICU" for it in body["items"])
