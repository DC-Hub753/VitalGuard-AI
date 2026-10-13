import asyncio

import pytest

from app.live_events import LiveEventHub


class FakeSocket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"limit": -1}, "Replay limit"),
        ({"limit": 101}, "Replay limit"),
        ({"limit": "50"}, "Replay limit"),
        ({"limit": True}, "Replay limit"),
        ({"after_event_id": 0}, "after_event_id"),
        ({"after_event_id": "12"}, "after_event_id"),
        ({"patient_id": ""}, "patient_id"),
        ({"patient_id": "P" * 65}, "patient_id"),
        ({"patient_id": 12}, "patient_id"),
    ],
)
def test_invalid_replay_payload_is_rejected_without_query(monkeypatch, payload, message):
    from app import ingestion_store

    def unexpected_query(**kwargs):
        raise AssertionError("Invalid replay payload must not query storage")

    monkeypatch.setattr(ingestion_store, "list_replayable_events", unexpected_query)

    async def scenario():
        socket = FakeSocket()
        await LiveEventHub().handle_replay_request(socket, payload)
        assert len(socket.events) == 1
        assert socket.events[0]["type"] == "error"
        assert message in socket.events[0]["message"]

    asyncio.run(scenario())


def test_replay_uses_validated_limit_and_returns_completion(monkeypatch):
    from app import ingestion_store

    calls = []

    def fake_query(**kwargs):
        calls.append(kwargs)
        return [{
            "type": "observation.created",
            "event_id": 8,
            "patient_id": "DEMO-001",
        }]

    monkeypatch.setattr(ingestion_store, "list_replayable_events", fake_query)

    async def scenario():
        socket = FakeSocket()
        await LiveEventHub().handle_replay_request(
            socket,
            {"after_event_id": 3, "patient_id": "DEMO-001", "limit": 100},
        )
        assert calls == [{
            "patient_id": "DEMO-001",
            "after_event_id": 3,
            "limit": 100,
        }]
        assert socket.events[0]["type"] == "event.replay"
        assert socket.events[0]["is_replay"] is True
        assert socket.events[1]["type"] == "replay.complete"
        assert socket.events[1]["count"] == 1

    asyncio.run(scenario())
