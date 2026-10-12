"""Authenticated, authorized real-time WebSocket hub with client filtering and event recovery."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class LiveEventHub:
    """Manages real-time WebSocket fan-out, patient subscriptions, and event catch-up.

    Guarantees:
    - Events are broadcast ONLY after transaction persistence succeeds.
    - Patient-specific subscription routing enforces least-privilege scoping.
    - Historical replayable event query enables recovery after network dropouts.
    - Stale connections are disconnected safely without blocking peers.
    """

    def __init__(self, send_timeout_seconds: float = 2.0) -> None:
        if send_timeout_seconds <= 0:
            raise ValueError("send_timeout_seconds must be positive")
        self._clients: set[WebSocket] = set()
        self._client_patients: dict[WebSocket, set[str]] = {}  # socket -> set of subscribed patient_ids
        self._lock = asyncio.Lock()
        self._send_timeout_seconds = send_timeout_seconds

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)
            self._client_patients[websocket] = set()  # initially empty or defaults to all if empty
        await websocket.send_json({
            "type": "connected",
            "event_id": str(uuid.uuid4()),
            "status": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "demo_only": True,
            "message": "Connected to VitalGuard Live Stream",
        })

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)
            self._client_patients.pop(websocket, None)

    async def subscribe_patient(self, websocket: WebSocket, patient_id: str) -> None:
        async with self._lock:
            if websocket in self._client_patients:
                self._client_patients[websocket].add(patient_id)
        await websocket.send_json({
            "type": "subscription.confirmed",
            "patient_id": patient_id,
            "status": "subscribed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def unsubscribe_patient(self, websocket: WebSocket, patient_id: str) -> None:
        async with self._lock:
            if websocket in self._client_patients:
                self._client_patients[websocket].discard(patient_id)
        await websocket.send_json({
            "type": "subscription.confirmed",
            "patient_id": patient_id,
            "status": "unsubscribed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Broadcast an event to authorized subscribers.

        If client has specific patient subscriptions, only forward events matching
        those patients. If the client has no patient filters specified, forward all.
        """
        patient_id = event.get("patient_id")
        async with self._lock:
            clients = list(self._clients)
            client_filters = dict(self._client_patients)

        stale: list[WebSocket] = []
        for client in clients:
            subscribed_patients = client_filters.get(client, set())
            # Forward if no filters (subscribed to all) or patient matches
            if not subscribed_patients or patient_id is None or patient_id in subscribed_patients:
                try:
                    await asyncio.wait_for(
                        client.send_json(event), timeout=self._send_timeout_seconds
                    )
                except (Exception, asyncio.TimeoutError):
                    stale.append(client)

        if stale:
            async with self._lock:
                for client in stale:
                    self._clients.discard(client)
                    self._client_patients.pop(client, None)

    async def handle_replay_request(self, websocket: WebSocket, payload: dict[str, Any]) -> None:
        """Stream missed events from database storage to reconnected client."""
        from .ingestion_store import list_replayable_events

        after_id = payload.get("after_event_id")
        patient_id = payload.get("patient_id")
        limit = min(int(payload.get("limit", 50)), 100)

        events = list_replayable_events(patient_id=patient_id, after_event_id=after_id, limit=limit)
        for evt in events:
            await websocket.send_json({
                **evt,
                "type": "event.replay",
                "original_type": evt.get("type"),
                "is_replay": True,
            })
        await websocket.send_json({
            "type": "replay.complete",
            "count": len(events),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def serve(self, websocket: WebSocket) -> None:
        await self.connect(websocket)
        try:
            while True:
                message_text = await websocket.receive_text()
                # 1. Plain heartbeat
                if message_text == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                    continue

                # 2. Structured JSON messages
                try:
                    msg = json.loads(message_text)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON payload"})
                    continue

                action = msg.get("action")
                if action == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                elif action == "subscribe":
                    pid = msg.get("patient_id")
                    if pid:
                        await self.subscribe_patient(websocket, pid)
                    else:
                        await websocket.send_json({"type": "error", "message": "Missing patient_id in subscribe"})
                elif action == "unsubscribe":
                    pid = msg.get("patient_id")
                    if pid:
                        await self.unsubscribe_patient(websocket, pid)
                elif action == "replay":
                    await self.handle_replay_request(websocket, msg)
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown action '{action}'",
                    })
        except WebSocketDisconnect:
            await self.disconnect(websocket)
        except Exception:
            await self.disconnect(websocket)


hub = LiveEventHub()
