import asyncio

import pytest

from app.live_events import LiveEventHub


class FakeSocket:
    def __init__(self, delay=0):
        self.delay = delay
        self.events = []

    async def send_json(self, event):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.events.append(event)


def test_hub_requires_positive_send_timeout():
    with pytest.raises(ValueError, match="positive"):
        LiveEventHub(send_timeout_seconds=0)


def test_slow_client_is_removed_without_blocking_healthy_client():
    async def scenario():
        hub = LiveEventHub(send_timeout_seconds=0.01)
        slow = FakeSocket(delay=0.1)
        healthy = FakeSocket()
        hub._clients.update({slow, healthy})

        await asyncio.wait_for(hub.broadcast({"type": "observation.created"}), timeout=0.2)

        assert healthy.events == [{"type": "observation.created"}]
        assert slow not in hub._clients
        assert healthy in hub._clients

    asyncio.run(scenario())


def test_failed_client_is_removed_and_other_clients_receive_event():
    class BrokenSocket:
        async def send_json(self, event):
            raise RuntimeError("disconnected")

    async def scenario():
        hub = LiveEventHub()
        broken = BrokenSocket()
        healthy = FakeSocket()
        hub._clients.update({broken, healthy})

        await hub.broadcast({"type": "alert.created"})

        assert broken not in hub._clients
        assert healthy.events == [{"type": "alert.created"}]

    asyncio.run(scenario())


def test_patient_filter_excludes_other_patients_and_unscoped_events():
    async def scenario():
        hub = LiveEventHub()
        scoped = FakeSocket()
        unfiltered = FakeSocket()
        hub._clients.update({scoped, unfiltered})
        hub._client_patients[scoped] = set()
        hub._client_patients[unfiltered] = set()

        # Explicit subscription switches this socket into scoped mode.
        await hub.subscribe_patient(scoped, "PATIENT-A")
        scoped.events.clear()  # ignore subscription confirmation

        await hub.broadcast({"type": "observation.created", "patient_id": "PATIENT-A"})
        await hub.broadcast({"type": "observation.created", "patient_id": "PATIENT-B"})
        await hub.broadcast({"type": "system.notice"})

        assert [event.get("patient_id") for event in scoped.events] == ["PATIENT-A"]
        assert len(unfiltered.events) == 3

    asyncio.run(scenario())


def test_unsubscribing_last_patient_does_not_restore_all_events():
    async def scenario():
        hub = LiveEventHub()
        scoped = FakeSocket()
        hub._clients.add(scoped)
        hub._client_patients[scoped] = set()

        await hub.subscribe_patient(scoped, "PATIENT-A")
        await hub.unsubscribe_patient(scoped, "PATIENT-A")
        scoped.events.clear()  # ignore subscription confirmations

        await hub.broadcast({"type": "observation.created", "patient_id": "PATIENT-A"})
        await hub.broadcast({"type": "observation.created", "patient_id": "PATIENT-B"})
        await hub.broadcast({"type": "system.notice"})

        assert scoped.events == []

    asyncio.run(scenario())
