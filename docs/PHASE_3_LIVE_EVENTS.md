# Phase 3 — Live event delivery

## Endpoint

Connect to `/api/v1/live` using WebSocket (wss on hosted HTTPS deployments, ws locally).

On connection the server sends:
```json
{"type":"connected","demo_only":true}
```

After a demo observation is saved successfully, connected clients receive:
```json
{
  "type": "observation.created",
  "event_id": 123,
  "patient_id": "DEMO-LIVE-001",
  "created_at": "database timestamp",
  "observation": {"heart_rate": 90},
  "prediction": {"risk_score": 50, "demo_only": true},
  "demo_only": true
}
```

The actual observation and prediction fields contain the full validated payload returned by the API. Client may send the text `ping` and receives a JSON `pong`.

Subscription messages must provide a non-empty string `patient_id` of at most 64 characters. Invalid subscription and unsubscription messages return an error envelope and leave the socket available for subsequent valid messages. Structured JSON messages must be objects.

## Recovery contract

WebSocket is a best-effort live notification channel, not the source of truth. Persist first, then broadcast. If a client disconnects, it must reconnect with exponential backoff and call `GET /api/v1/observations?limit=100` to reconcile persisted records. Use observation IDs as event cursors and deduplicate by ID.

## Replay request bounds

Replay requests accept an optional positive integer `after_event_id`, an optional non-empty `patient_id` up to 64 characters, and a `limit` from 1 to 100 (default 50). Invalid fields receive an error response without querying storage. Replay sends use the hub's bounded send timeout so a stalled socket cannot hold replay delivery indefinitely.

## Current limitations

- In-memory fan-out works within a single backend process only. Multiple Render instances need a shared broker or database-backed outbox.
- This phase provides event delivery primitives and tests, but the React dashboard has not yet been wired to the socket.
- No authenticated socket access or patient-level authorization is implemented yet.
- Synthetic demonstration data only; not for clinical use.
