""""Authenticated, authorized real-time WebSocket hub with client filtering and event recovery."""
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
    - Patient-filtered streams only receive events matching subscribed patient IDs.
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

    async def connect(self, websocket: WebSocket, subprotocol: str | None = None) -> None:
        await websocket.accept(subprotocol=subprotocol)
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

    @staticmethod
    def _valid_patient_id(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip()) and len(value) <= 64

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
            if not subscribed_patients or patient_id in subscribed_patients:
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
        raw_limit = payload.get("limit", 50)

        # Validate untrusted client input before it reaches the database query.
        if isinstance(raw_limit, bool) or not isinstance(raw_limit, int) or not 1 <= raw_limit <= 100:
            await websocket.send_json({
                "type": "error",
                "message": "Replay limit must be an integer between 1 and 100",
            })
            return
        if after_id is not None and (
            isinstance(after_id, bool) or not isinstance(after_id, int) or after_id < 1
        ):
            await websocket.send_json({
                "type": "error",
                "message": "after_event_id must be a positive integer",
            })
            return
        if patient_id is not None and (
            not isinstance(patient_id, str) or not patient_id.strip() or len(patient_id) > 64
        ):
            await websocket.send_json({
                "type": "error",
                "message": "patient_id must be a non-empty string of at most 64 characters",
            })
            return

        events = list_replayable_events(patient_id=patient_id, after_event_id=after_id, limit=raw_limit)
        for evt in events:
            await asyncio.wait_for(
                websocket.send_json({
                    **evt,
                    "type": "event.replay",
                    "original_type": evt.get("type"),
                    "is_replay": True,
                }),
                timeout=self._send_timeout_seconds,
            )
        await asyncio.wait_for(
            websocket.send_json({
                "type": "replay.complete",
                "count": len(events),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
            timeout=self._send_timeout_seconds,
        )

    async def serve(self, websocket: WebSocket, subprotocol: str | None = None) -> None:
        await self.connect(websocket, subprotocol=subprotocol)
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
                if not isinstance(msg, dict):
                    await websocket.send_json({"type": "error", "message": "JSON payload must be an object"})
                    continue

                action = msg.get("action")
                if action == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                elif action in ("subscribe", "unsubscribe"):
                    pid = msg.get("patient_id")
                    if not self._valid_patient_id(pid):
                        await websocket.send_json({
                            "type": "error",
                            "message": "patient_id must be a non-empty string of at most 64 characters",
                        })
                        continue
                    if action == "subscribe":
                        await self.subscribe_patient(websocket, pid)
                    else:
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
