"""Durable alert lifecycle, deduplication, and escalation audit service."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal
from sqlalchemy import desc, insert, select, update
from sqlalchemy.exc import IntegrityError

from .storage import _engine
from .storage_schema import alerts, audit_events

AlertStatus = Literal["open", "acknowledged", "assigned", "resolved", "reopened"]
AlertType = Literal["clinical_rule", "ml_derived", "trend_warning", "data_quality", "connectivity_failure"]
AlertSeverity = Literal["low", "medium", "high", "critical"]

VALID_STATUSES: set[AlertStatus] = {"open", "acknowledged", "assigned", "resolved", "reopened"}

VALID_TRANSITIONS: dict[str, set[str]] = {
    "open": {"acknowledged", "assigned", "resolved"},
    "acknowledged": {"assigned", "resolved", "reopened"},
    "assigned": {"acknowledged", "assigned", "resolved", "reopened"},
    "resolved": {"reopened"},
    "reopened": {"acknowledged", "assigned", "resolved"},
}

ESCALATION_DEADLINES_MINUTES: dict[str, int] = {
    "critical": 15,
    "high": 30,
    "medium": 60,
    "low": 120,
}


def _serialize(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("created_at", "acknowledged_at", "resolved_at", "assigned_at", "reopened_at"):
        if item.get(key) is not None and hasattr(item[key], "isoformat"):
            item[key] = item[key].isoformat()
    if "details_json" in item:
        item["details"] = json.loads(item.pop("details_json"))
    if "notes_json" in item:
        item["notes"] = json.loads(item.pop("notes_json"))
    return item


def _record_audit(connection, entity_id: str, action: str, actor: str, details: dict[str, Any]) -> None:
    connection.execute(insert(audit_events).values(
        entity_type="alert",
        entity_id=entity_id,
        action=action,
        actor=actor,
        details_json=json.dumps(details, separators=(",", ":"), sort_keys=True),
    ))


def create_or_deduplicate_alert(
    *,
    patient_id: str,
    event_key: str,
    severity: AlertSeverity,
    title: str,
    alert_type: AlertType = "clinical_rule",
    details: dict[str, Any] | None = None,
    created_by: str = "demo-system",
) -> dict[str, Any]:
    """Create a new alert or deduplicate against existing active alerts for the same condition."""
    engine = _engine()
    details_dict = details or {}
    now = datetime.now(timezone.utc)

    try:
        with engine.begin() as connection:
            # 1. Exact event_key idempotency check
            existing_exact = connection.execute(
                select(alerts).where(alerts.c.event_key == event_key)
            ).mappings().first()
            if existing_exact:
                return _serialize(existing_exact)

            # 2. Deduplication check: check if an active alert of the same type exists for this patient
            active_alert = connection.execute(
                select(alerts).where(
                    alerts.c.patient_id == patient_id,
                    alerts.c.alert_type == alert_type,
                    alerts.c.status.in_(["open", "acknowledged", "assigned", "reopened"]),
                ).order_by(desc(alerts.c.id))
            ).mappings().first()

            if active_alert:
                # Deduplicate: update details with latest trigger without creating duplicate alert
                existing_details = json.loads(active_alert["details_json"])
                existing_details["latest_trigger"] = {
                    "event_key": event_key,
                    "timestamp": now.isoformat(),
                    "title": title,
                    **details_dict,
                }
                connection.execute(
                    update(alerts)
                    .where(alerts.c.id == active_alert["id"])
                    .values(details_json=json.dumps(existing_details, separators=(",", ":")))
                )
                _record_audit(
                    connection,
                    str(active_alert["id"]),
                    "deduplicated_update",
                    created_by,
                    {"event_key": event_key, "severity": severity},
                )
                updated = connection.execute(
                    select(alerts).where(alerts.c.id == active_alert["id"])
                ).mappings().one()
                return _serialize(updated)

            # 3. Create fresh alert
            result = connection.execute(insert(alerts).values(
                patient_id=patient_id,
                event_key=event_key,
                severity=severity,
                status="open",
                title=title,
                alert_type=alert_type,
                details_json=json.dumps(details_dict, separators=(",", ":")),
                notes_json="[]",
                created_at=now,
            ))
            alert_id = result.inserted_primary_key[0]
            _record_audit(
                connection,
                str(alert_id),
                "created",
                created_by,
                {"severity": severity, "alert_type": alert_type, "event_key": event_key},
            )
            created = connection.execute(
                select(alerts).where(alerts.c.id == alert_id)
            ).mappings().one()
            return _serialize(created)

    except IntegrityError:
        # Race condition handling for unique event_key
        with engine.connect() as connection:
            row = connection.execute(select(alerts).where(alerts.c.event_key == event_key)).mappings().first()
            return _serialize(row) if row else {}
    finally:
        engine.dispose()


def create_alert(
    *,
    patient_id: str,
    event_key: str,
    severity: str,
    title: str,
    details: dict | None = None,
    alert_type: str = "clinical_rule",
) -> dict | None:
    """Backward compatible wrapper around create_or_deduplicate_alert."""
    return create_or_deduplicate_alert(
        patient_id=patient_id,
        event_key=event_key,
        severity=severity,  # type: ignore[arg-type]
        title=title,
        alert_type=alert_type,  # type: ignore[arg-type]
        details=details,
    )


def transition_alert_state(
    alert_id: int,
    *,
    action: Literal["acknowledge", "assign", "resolve", "reopen", "add_note"],
    actor: str,
    assignee: str | None = None,
    note: str | None = None,
) -> dict[str, Any] | None:
    """Enforce valid alert lifecycle transitions with complete audit logging."""
    engine = _engine()
    now = datetime.now(timezone.utc)

    try:
        with engine.begin() as connection:
            row = connection.execute(
                select(alerts).where(alerts.c.id == alert_id)
            ).mappings().first()
            if not row:
                return None

            current_status = row["status"]
            notes_list = json.loads(row["notes_json"]) if row["notes_json"] else []

            # Determine target status and validate transition
            if action == "acknowledge":
                target_status = "acknowledged"
                if target_status not in VALID_TRANSITIONS.get(current_status, set()):
                    raise ValueError(f"Cannot transition alert from '{current_status}' to '{target_status}'")
                updates = {
                    "status": target_status,
                    "acknowledged_by": actor,
                    "acknowledged_at": now,
                }
            elif action == "assign":
                if not assignee:
                    raise ValueError("Assignee is required for 'assign' action")
                target_status = "assigned"
                if target_status not in VALID_TRANSITIONS.get(current_status, set()) and current_status != "assigned":
                    raise ValueError(f"Cannot transition alert from '{current_status}' to '{target_status}'")
                updates = {
                    "status": target_status,
                    "assigned_to": assignee,
                    "assigned_at": now,
                }
            elif action == "resolve":
                target_status = "resolved"
                if target_status not in VALID_TRANSITIONS.get(current_status, set()):
                    raise ValueError(f"Cannot transition alert from '{current_status}' to '{target_status}'")
                updates = {
                    "status": target_status,
                    "resolved_at": now,
                }
            elif action == "reopen":
                target_status = "reopened"
                if target_status not in VALID_TRANSITIONS.get(current_status, set()):
                    raise ValueError(f"Cannot transition alert from '{current_status}' to '{target_status}'")
                updates = {
                    "status": target_status,
                    "reopened_by": actor,
                    "reopened_at": now,
                    "resolved_at": None,
                }
            elif action == "add_note":
                if not note:
                    raise ValueError("Note content is required")
                target_status = current_status
                updates = {}
            else:
                raise ValueError(f"Unsupported alert action: '{action}'")

            # Append note if provided
            if note:
                notes_list.append({
                    "author": actor,
                    "action": action,
                    "text": note,
                    "timestamp": now.isoformat(),
                })
                updates["notes_json"] = json.dumps(notes_list, separators=(",", ":"))

            if updates:
                connection.execute(
                    update(alerts).where(alerts.c.id == alert_id).values(**updates)
                )

            audit_action = {
                "acknowledge": "acknowledged",
                "resolve": "resolved",
                "assign": "assigned",
                "reopen": "reopened",
                "add_note": "note_added",
            }.get(action, action)

            # Record non-repudiable audit event
            _record_audit(
                connection,
                str(alert_id),
                audit_action,
                actor,
                {
                    "previous_status": current_status,
                    "new_status": target_status,
                    "assignee": assignee,
                    "note": note,
                },
            )

            updated_row = connection.execute(
                select(alerts).where(alerts.c.id == alert_id)
            ).mappings().one()
            return _serialize(updated_row)

    finally:
        engine.dispose()


def transition_alert(alert_id: int, action: str, actor: str) -> dict | None:
    """Backward compatibility wrapper."""
    return transition_alert_state(alert_id, action=action, actor=actor)  # type: ignore[arg-type]


def list_alerts(
    status: str | None = None,
    patient_id: str | None = None,
    alert_type: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List alerts with filtering and escalation status."""
    engine = _engine()
    now = datetime.now(timezone.utc)
    try:
        query = select(alerts)
        if status:
            query = query.where(alerts.c.status == status)
        if patient_id:
            query = query.where(alerts.c.patient_id == patient_id)
        if alert_type:
            query = query.where(alerts.c.alert_type == alert_type)
        if severity:
            query = query.where(alerts.c.severity == severity)

        query = query.order_by(desc(alerts.c.id)).limit(limit)

        with engine.connect() as connection:
            rows = connection.execute(query).mappings().all()

        results = []
        for row in rows:
            item = _serialize(row)
            # Compute escalation deadline status
            if item["status"] in ("open", "reopened"):
                created_at = row["created_at"]
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                age_minutes = max(0.0, (now - created_at).total_seconds() / 60.0)
                deadline = ESCALATION_DEADLINES_MINUTES.get(item["severity"], 60)
                item["age_minutes"] = round(age_minutes, 1)
                item["deadline_minutes"] = deadline
                item["is_overdue"] = age_minutes > deadline
            else:
                item["is_overdue"] = False
            results.append(item)

        return results
    finally:
        engine.dispose()


def list_alert_audit(alert_id: int) -> list[dict[str, Any]]:
    """Fetch complete immutable audit timeline for an alert."""
    engine = _engine()
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                select(audit_events)
                .where(
                    audit_events.c.entity_type == "alert",
                    audit_events.c.entity_id == str(alert_id),
                )
                .order_by(audit_events.c.id.asc())
            ).mappings().all()

        output = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            if item.get("created_at") is not None and hasattr(item["created_at"], "isoformat"):
                item["created_at"] = item["created_at"].isoformat()
            output.append(item)
        return output
    finally:
        engine.dispose()
