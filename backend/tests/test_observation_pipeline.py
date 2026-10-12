"""Phase 3 test suite: Canonical observation ingestion, real-time event pipeline, and provenance."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.observation_contract import (
    CanonicalObservation,
    ObservationUnits,
    VitalsMeasurements,
    evaluate_vitals_quality,
)
from app.patient_service import create_patient
from auth_helpers import authenticate_test_client


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VITALGUARD_DB_PATH", str(tmp_path / "pipeline.sqlite3"))
    with TestClient(app) as test_client:
        authenticate_test_client(test_client)
        yield test_client


def make_vitals(**overrides):
    base = {
        "heart_rate": 78.0,
        "spo2": 98.0,
        "systolic_bp": 120.0,
        "diastolic_bp": 80.0,
        "temperature": 36.8,
        "respiratory_rate": 16.0,
        "age": 55,
    }
    base.update(overrides)
    return base


def make_canonical_payload(patient_id="DEMO-P001", event_id="evt-001", **vitals_overrides):
    return {
        "source_system": "mon-bedside-12",
        "source_event_id": event_id,
        "source_mode": "synthetic_demo",
        "patient_id": patient_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "measurements": make_vitals(**vitals_overrides),
        "units": {
            "heart_rate": "bpm",
            "spo2": "percent",
            "systolic_bp": "mmHg",
            "diastolic_bp": "mmHg",
            "temperature": "degC",
            "respiratory_rate": "breaths/min",
        },
    }


def test_canonical_contract_validates_pulse_pressure_and_ranges():
    # Diastolic BP >= Systolic BP must be rejected
    with pytest.raises(ValueError, match="diastolic_bp .* must be strictly lower than systolic_bp"):
        VitalsMeasurements(**make_vitals(systolic_bp=100.0, diastolic_bp=110.0))

    # Equal BP rejected
    with pytest.raises(ValueError, match="must be strictly lower"):
        VitalsMeasurements(**make_vitals(systolic_bp=120.0, diastolic_bp=120.0))

    # Valid measurements pass
    valid = VitalsMeasurements(**make_vitals(systolic_bp=120.0, diastolic_bp=80.0))
    assert valid.systolic_bp == 120.0


def test_physiological_bounds_distinguished_from_clinical_abnormality():
    # 1. Clinically abnormal but physiologically plausible (e.g. tachycardia HR 125, SpO2 91%)
    abnormal_vitals = VitalsMeasurements(**make_vitals(heart_rate=125.0, spo2=91.0))
    quality = evaluate_vitals_quality(abnormal_vitals)
    assert quality.is_plausible is True
    assert quality.is_abnormal is True
    assert quality.quality_score == 1.0
    assert len(quality.warnings) == 0

    # 2. Physiologically implausible (e.g. core temp 44.5 degC, HR 280 bpm)
    implausible_vitals = VitalsMeasurements(**make_vitals(heart_rate=280.0, temperature=44.5))
    quality_imp = evaluate_vitals_quality(implausible_vitals)
    assert quality_imp.is_plausible is False
    assert quality_imp.quality_score < 1.0
    assert len(quality_imp.warnings) >= 2


def test_ingest_canonical_observation_persists_before_websocket_broadcast(client):
    token = client.headers["Authorization"].split(" ", 1)[1]
    payload = make_canonical_payload(patient_id="DEMO-P001", event_id="evt-canon-101")

    with client.websocket_connect(f"/api/v1/live?token={token}") as websocket:
        init_evt = websocket.receive_json()
        assert init_evt["type"] == "connected"

        res = client.post("/api/v1/ingestion/observation", json=payload)
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "accepted"
        assert body["observation_id"] > 0

        # Verify event reached subscriber without page refresh
        event = websocket.receive_json()
        assert event["type"] == "observation.created"
        assert event["event_id"] == body["observation_id"]
        assert event["patient_id"] == "DEMO-P001"
        assert event["source_mode"] == "synthetic_demo"


def test_duplicate_submission_is_idempotent(client):
    payload = make_canonical_payload(patient_id="DEMO-P002", event_id="evt-idemp-001")
    first = client.post("/api/v1/ingestion/observation", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "accepted"
    obs_id = first.json()["observation_id"]

    # Ingest same event again
    second = client.post("/api/v1/ingestion/observation", json=payload)
    assert second.status_code == 200
    body2 = second.json()
    assert body2["status"] == "duplicate"
    assert body2["observation_id"] == obs_id


def test_out_of_order_observation_recorded_with_diagnostic(client):
    now = datetime.now(timezone.utc)
    # 1. Ingest newer reading
    t_newer = now
    p_newer = make_canonical_payload(patient_id="DEMO-P003", event_id="evt-order-new")
    p_newer["observed_at"] = t_newer.isoformat()
    res1 = client.post("/api/v1/ingestion/observation", json=p_newer)
    assert res1.json()["status"] == "accepted"
    assert res1.json().get("out_of_order") is False

    # 2. Ingest older reading arriving out-of-order
    t_older = now - timedelta(hours=2)
    p_older = make_canonical_payload(patient_id="DEMO-P003", event_id="evt-order-old")
    p_older["observed_at"] = t_older.isoformat()
    res2 = client.post("/api/v1/ingestion/observation", json=p_older)
    assert res2.json()["status"] == "accepted"
    assert res2.json().get("out_of_order") is True
    assert any("out of order" in w for w in res2.json()["quality"].get("warnings", []))


def test_patient_existence_validation(client):
    # Register patient in database
    create_patient(patient_id="DEMO-KNOWN-01", display_name="Known Patient", ward="Ward A")

    # Ingest for registered patient -> accepted
    p_known = make_canonical_payload(patient_id="DEMO-KNOWN-01", event_id="evt-known-01")
    res_known = client.post("/api/v1/ingestion/observation?require_known_patient=true", json=p_known)
    assert res_known.json()["status"] == "accepted"

    # Ingest for unregistered patient -> rejected with diagnostic
    p_unknown = make_canonical_payload(patient_id="DEMO-UNKNOWN-99", event_id="evt-unknown-99")
    res_unknown = client.post("/api/v1/ingestion/observation?require_known_patient=true", json=p_unknown)
    assert res_unknown.json()["status"] == "rejected"
    assert res_unknown.json()["diagnostic"] == "patient_not_found"


def test_historical_replay_adapter_labels_provenance(client):
    historical_data = {
        "source_name": "mimic-iv-sample-dataset",
        "records": [
            {
                "patient_id": "DEMO-HIST-01",
                "event_id": "hist-rec-001",
                "observed_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
                "vitals": make_vitals(heart_rate=88.0, spo2=97.0),
                "units": {"heart_rate": "bpm", "spo2": "percent"},
            },
            {
                "patient_id": "DEMO-HIST-02",
                "event_id": "hist-rec-002",
                "observed_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                "vitals": make_vitals(heart_rate=72.0, spo2=99.0),
            },
        ],
    }

    res = client.post("/api/v1/ingestion/replay", json=historical_data)
    assert res.status_code == 200
    body = res.json()
    assert body["accepted"] == 2
    assert body["source_mode"] == "historical_replay"
    assert "historical replay data" in body["provenance_note"]
    for item in body["items"]:
        assert item["source_mode"] == "historical_replay"


def test_websocket_patient_subscription_scoping(client):
    token = client.headers["Authorization"].split(" ", 1)[1]

    with client.websocket_connect(f"/api/v1/live?token={token}") as ws_sub1, \
         client.websocket_connect(f"/api/v1/live?token={token}") as ws_sub2:

        assert ws_sub1.receive_json()["type"] == "connected"
        assert ws_sub2.receive_json()["type"] == "connected"

        # ws_sub1 subscribes strictly to PATIENT-ALPHA
        ws_sub1.send_text(json.dumps({"action": "subscribe", "patient_id": "PATIENT-ALPHA"}))
        sub_resp = ws_sub1.receive_json()
        assert sub_resp["type"] == "subscription.confirmed"
        assert sub_resp["patient_id"] == "PATIENT-ALPHA"

        # ws_sub2 subscribes strictly to PATIENT-BETA
        ws_sub2.send_text(json.dumps({"action": "subscribe", "patient_id": "PATIENT-BETA"}))
        sub_resp2 = ws_sub2.receive_json()
        assert sub_resp2["type"] == "subscription.confirmed"
        assert sub_resp2["patient_id"] == "PATIENT-BETA"

        # Ingest reading for PATIENT-ALPHA
        client.post("/api/v1/ingestion/observation", json=make_canonical_payload(patient_id="PATIENT-ALPHA", event_id="evt-alpha-1"))

        # ws_sub1 must receive it
        evt = ws_sub1.receive_json()
        assert evt["type"] == "observation.created"
        assert evt["patient_id"] == "PATIENT-ALPHA"

        # Ping ws_sub2 to ensure socket is responsive without having received alpha's observation
        ws_sub2.send_text(json.dumps({"action": "ping"}))
        pong = ws_sub2.receive_json()
        assert pong["type"] == "pong"


def test_missed_event_recovery_via_websocket_and_rest(client):
    # Ingest 3 observations while client is not connected
    for i in range(1, 4):
        p = make_canonical_payload(patient_id="DEMO-RECOVER-01", event_id=f"evt-rec-{i}")
        client.post("/api/v1/ingestion/observation", json=p)

    # 1. Recover via REST endpoint
    rest_res = client.get("/api/v1/ingestion/events?patient_id=DEMO-RECOVER-01&limit=10")
    assert rest_res.status_code == 200
    events = rest_res.json()["events"]
    assert len(events) == 3
    first_event_id = events[0]["event_id"]

    # 2. Recover via WebSocket replay request
    token = client.headers["Authorization"].split(" ", 1)[1]
    with client.websocket_connect(f"/api/v1/live?token={token}") as websocket:
        assert websocket.receive_json()["type"] == "connected"

        # Request events after first_event_id
        websocket.send_text(json.dumps({
            "action": "replay",
            "patient_id": "DEMO-RECOVER-01",
            "after_event_id": first_event_id,
        }))

        replayed_1 = websocket.receive_json()
        assert replayed_1["type"] == "event.replay"
        assert replayed_1["event_id"] == events[1]["event_id"]

        replayed_2 = websocket.receive_json()
        assert replayed_2["type"] == "event.replay"
        assert replayed_2["event_id"] == events[2]["event_id"]

        complete = websocket.receive_json()
        assert complete["type"] == "replay.complete"
        assert complete["count"] == 2


def test_freshness_status_transitions(client):
    # 1. Unknown patient has no data
    fresh_none = client.get("/api/v1/ingestion/freshness/DEMO-NONEXISTENT")
    assert fresh_none.json()["status"] == "disconnected"
    assert fresh_none.json()["has_data"] is False

    # 2. Fresh observation
    p = make_canonical_payload(patient_id="DEMO-FRESH-01", event_id="evt-fresh-01")
    client.post("/api/v1/ingestion/observation", json=p)

    fresh_check = client.get("/api/v1/ingestion/freshness/DEMO-FRESH-01?stale_threshold_seconds=300")
    assert fresh_check.json()["status"] == "connected"
    assert fresh_check.json()["freshness"] == "fresh"
    assert fresh_check.json()["source_mode"] == "synthetic_demo"

    # 3. Reading older than stale threshold becomes stale
    stale_check = client.get("/api/v1/ingestion/freshness/DEMO-FRESH-01?stale_threshold_seconds=0")
    assert stale_check.json()["freshness"] == "stale"
    assert stale_check.json()["status"] == "stale"
