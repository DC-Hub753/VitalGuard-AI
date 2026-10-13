from app.trends import summarize_observation_trends


def record(record_id, heart_rate, spo2, score, timestamp):
    return {
        "id": record_id,
        "patient_id": "DEMO-TREND-001",
        "created_at": timestamp,
        "inputs": {"heart_rate": heart_rate, "spo2": spo2, "systolic_bp": 120,
                   "temperature": 37.0, "respiratory_rate": 16},
        "prediction": {"risk_score": score},
    }


def test_trend_summary_reports_descriptive_increases_and_decreases():
    records = [
        record(1, 70, 99, 20, "2026-10-10T10:00:00+00:00"),
        record(2, 80, 97, 40, "2026-10-10T10:01:00+00:00"),
        record(3, 90, 95, 60, "2026-10-10T10:02:00+00:00"),
    ]
    result = summarize_observation_trends("DEMO-TREND-001", records)
    trends = {item["metric"]: item for item in result["trends"]}
    assert trends["heart_rate"]["direction"] == "increasing"
    assert trends["spo2"]["direction"] == "decreasing"
    assert trends["risk_score"]["absolute_change"] == 40
    assert result["observation_count"] == 3
    assert result["demo_only"] is True
    assert result["clinically_validated"] is False
    assert "No future values are forecast" in result["interpretation"]


def test_trend_summary_flags_insufficient_data():
    result = summarize_observation_trends("DEMO-TREND-001", [
        record(1, 70, 99, 20, "2026-10-10T10:00:00+00:00"),
    ])
    assert all(item["status"] == "insufficient_data" for item in result["trends"])



def test_trend_summary_uses_timestamp_chronology_not_record_id():
    records = [
        record(30, 90, 95, 60, "2026-10-10T10:02:00+00:00"),
        record(10, 70, 99, 20, "2026-10-10T10:00:00+00:00"),
        record(20, 80, 97, 40, "2026-10-10T10:01:00+00:00"),
    ]

    result = summarize_observation_trends("DEMO-TREND-001", records)
    trends = {item["metric"]: item for item in result["trends"]}

    assert trends["heart_rate"]["first_value"] == 70
    assert trends["heart_rate"]["latest_value"] == 90
    assert trends["risk_score"]["absolute_change"] == 40
    assert result["first_observed_at"] == "2026-10-10T10:00:00+00:00"
    assert result["last_observed_at"] == "2026-10-10T10:02:00+00:00"


def test_trend_summary_ignores_non_numeric_and_non_finite_values():
    bad = record(2, float("nan"), float("inf"), float("-inf"), "2026-10-10T10:01:00+00:00")
    good = record(1, 70, 99, 20, "2026-10-10T10:00:00+00:00")
    result = summarize_observation_trends("DEMO-TREND-001", [bad, good])
    trends = {item["metric"]: item for item in result["trends"]}

    assert trends["heart_rate"]["sample_count"] == 1
    assert trends["heart_rate"]["status"] == "insufficient_data"
    assert trends["spo2"]["sample_count"] == 1
    assert trends["risk_score"]["sample_count"] == 1


def test_trend_summary_ignores_malformed_numeric_values():
    first = record(1, 70, 99, 20, "2026-10-10T10:00:00+00:00")
    second = record(2, "unknown", None, "invalid", "2026-10-10T10:01:00+00:00")
    result = summarize_observation_trends("DEMO-TREND-001", [first, second])
    trends = {item["metric"]: item for item in result["trends"]}

    assert trends["heart_rate"]["sample_count"] == 1
    assert trends["spo2"]["sample_count"] == 1
    assert trends["risk_score"]["sample_count"] == 1
