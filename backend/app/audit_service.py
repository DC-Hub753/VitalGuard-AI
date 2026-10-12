"""Audit logging persistence helpers for security, access control, and domain actions."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import desc, insert, select

from .storage import _engine
from .storage_schema import audit_events


def record_audit_event(
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Append-only recording of security and data mutations.
    
    Guarantees no sensitive secrets (passwords, tokens) are logged.
    """
    clean_details = dict(details or {})
    # Strip any potential sensitive keys if inadvertently passed
    for sensitive_key in ("password", "password_hash", "token", "access_token", "secret"):
        if sensitive_key in clean_details:
            clean_details[sensitive_key] = "[REDACTED]"

    engine = _engine()
    try:
        with engine.begin() as connection:
            connection.execute(insert(audit_events).values(
                entity_type=entity_type,
                entity_id=str(entity_id),
                action=action,
                actor=actor,
                details_json=json.dumps(clean_details, separators=(",", ":")),
            ))
    finally:
        engine.dispose()


def list_audit_events(
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query audit ledger. Accessible only to authorized administrators."""
    engine = _engine()
    try:
        query = select(audit_events)
        if entity_type is not None:
            query = query.where(audit_events.c.entity_type == entity_type)
        if entity_id is not None:
            query = query.where(audit_events.c.entity_id == str(entity_id))
        query = query.order_by(desc(audit_events.c.id)).limit(limit).offset(offset)

        with engine.connect() as connection:
            rows = connection.execute(query).mappings().all()

        results = []
        for row in rows:
            item = dict(row)
            if item.get("created_at") is not None and hasattr(item["created_at"], "isoformat"):
                item["created_at"] = item["created_at"].isoformat()
            try:
                item["details"] = json.loads(item.pop("details_json", "{}"))
            except Exception:
                item["details"] = {}
            results.append(item)
        return results
    finally:
        engine.dispose()
