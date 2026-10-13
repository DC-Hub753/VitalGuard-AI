"""Security regression tests for the authorized-feed adapter contract."""
from datetime import datetime, timezone

import pytest

from app.adapters.authorized_feed_adapter import AuthorizedFeedAdapter


def valid_payload(**overrides):
    payload = {
        "feed_auth_key": "feed-secret",
        "source_event_id": "device-event-001",
        "patient_id": "DEMO-FEED-001",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "measurements": {
            "heart_rate": 78.0,
            "spo2": 98.0,
            "systolic_bp": 120.0,
            "diastolic_bp": 80.0,
            "temperature": 36.8,
            "respiratory_rate": 16.0,
            "age": 55,
        },
        "units": {
            "heart_rate": "bpm",
            "spo2": "percent",
            "systolic_bp": "mmHg",
            "diastolic_bp": "mmHg",
            "temperature": "degC",
            "respiratory_rate": "breaths/min",
            "age": "years",
        },
    }
    payload.update(overrides)
    return payload


def test_authorized_feed_fails_closed_when_secret_is_not_configured():
    adapter = AuthorizedFeedAdapter(source_name="demo-device")

    with pytest.raises(PermissionError, match="missing or invalid feed credentials"):
        adapter.transform(valid_payload())


@pytest.mark.parametrize("credential", [None, "", "wrong-secret"])
def test_authorized_feed_rejects_missing_or_wrong_credentials(credential):
    adapter = AuthorizedFeedAdapter(source_name="demo-device", feed_key="feed-secret")
    payload = valid_payload(feed_auth_key=credential)

    with pytest.raises(PermissionError, match="missing or invalid feed credentials"):
        adapter.transform(payload)


def test_authorized_feed_accepts_configured_secret_and_excludes_it_from_canonical_data():
    adapter = AuthorizedFeedAdapter(source_name="demo-device", feed_key="feed-secret")

    canonical = adapter.transform(valid_payload())

    assert canonical.source_system == "demo-device"
    assert canonical.source_mode == "authorized_feed"
    assert canonical.source_event_id == "device-event-001"
    assert "feed_auth_key" not in canonical.model_dump()
