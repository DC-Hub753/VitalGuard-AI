"""HTTP endpoints for durable alert lifecycle, prioritization, and escalation."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from .alert_service import list_alert_audit, list_alerts, transition_alert_state
from .audit_service import record_audit_event
from .auth import authenticate_principal, require_permission
from .escalation_policy import evaluate_escalation
from .live_events import hub
from .permissions import (
    PERM_ALERTS_ACKNOWLEDGE,
    PERM_ALERTS_READ,
    PERM_ALERTS_RESOLVE,
    PERM_AUDIT_READ,
)
from .prioritization_service import prioritize_patients

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"], dependencies=[Depends(authenticate_principal)])


class AcknowledgePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    actor: str | None = None
    note: str | None = Field(default=None, max_length=500)


class AssignPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    assignee: str = Field(min_length=1, max_length=120)
    actor: str | None = None
    note: str | None = Field(default=None, max_length=500)


class ResolvePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    actor: str | None = None
    note: str | None = Field(default=None, max_length=500)


class ReopenPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    actor: str | None = None
    reason: str | None = Field(default=None, max_length=500)


class NotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1000)


@router.get("")
def get_alerts(
    status: Literal["open", "acknowledged", "assigned", "resolved", "reopened"] | None = None,
    alert_type: Literal["clinical_rule", "ml_derived", "trend_warning", "data_quality", "connectivity_failure"] | None = None,
    severity: Literal["low", "medium", "high", "critical"] | None = None,
    patient_id: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=50, ge=1, le=100),
    principal: dict = Depends(require_permission(PERM_ALERTS_READ)),
):
    """List alerts with filtering across lifecycle status, alert type, severity, and patient."""
    items = list_alerts(status=status, alert_type=alert_type, severity=severity, patient_id=patient_id, limit=limit)
    return {
        "items": items,
        "count": len(items),
        "demo_only": True,
    }


@router.get("/prioritization")
def get_patient_prioritization(
    ward: str | None = Query(default=None, max_length=80),
    risk_category: str | None = Query(default=None),
    has_open_alerts: bool | None = Query(default=None),
    stale_only: bool = Query(default=False),
    sort_by: Literal["priority", "news2_desc", "ml_desc", "patient_id"] = Query(default="priority"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: dict = Depends(require_permission(PERM_ALERTS_READ)),
):
    """Retrieve dynamic clinical patient priority ranking and risk stratification."""
    return prioritize_patients(
        ward=ward,
        risk_category=risk_category,
        has_open_alerts=has_open_alerts,
        stale_only=stale_only,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )


@router.get("/escalation-preview")
def get_escalation_preview(
    limit: int = Query(default=100, ge=1, le=100),
    principal: dict = Depends(require_permission(PERM_ALERTS_READ)),
):
    """Preview overdue alerts based on severity deadlines; never sends unrecorded notifications."""
    items = list_alerts(status="open", limit=limit)
    previews = [evaluate_escalation(item) for item in items]
    due = [item for item in previews if item["review_due"]]
    return {
        "items": previews,
        "count": len(previews),
        "due_count": len(due),
        "policy_version": previews[0]["policy_version"] if previews else "demo-escalation-policy-0.1.0",
        "demo_only": True,
        "notifications_sent": False,
        "clinical_policy": False,
    }


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    payload: AcknowledgePayload | None = None,
    principal: dict = Depends(require_permission(PERM_ALERTS_ACKNOWLEDGE)),
):
    note = payload.note if payload else None
    try:
        result = transition_alert_state(alert_id, action="acknowledge", actor=principal["sub"], note=note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    await hub.broadcast({
        "type": "alert.updated",
        "event_id": alert_id,
        "alert": result,
        "action": "acknowledge",
        "actor": principal["sub"],
        "demo_only": True,
    })
    return {"item": result, "demo_only": True}


@router.post("/{alert_id}/assign")
async def assign_alert(
    alert_id: int,
    payload: AssignPayload,
    principal: dict = Depends(require_permission(PERM_ALERTS_ACKNOWLEDGE)),
):
    try:
        result = transition_alert_state(
            alert_id,
            action="assign",
            actor=principal["sub"],
            assignee=payload.assignee,
            note=payload.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    await hub.broadcast({
        "type": "alert.updated",
        "event_id": alert_id,
        "alert": result,
        "action": "assign",
        "assignee": payload.assignee,
        "actor": principal["sub"],
        "demo_only": True,
    })
    return {"item": result, "demo_only": True}


@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    payload: ResolvePayload | None = None,
    principal: dict = Depends(require_permission(PERM_ALERTS_RESOLVE)),
):
    note = payload.note if payload else None
    try:
        result = transition_alert_state(alert_id, action="resolve", actor=principal["sub"], note=note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    await hub.broadcast({
        "type": "alert.updated",
        "event_id": alert_id,
        "alert": result,
        "action": "resolve",
        "actor": principal["sub"],
        "demo_only": True,
    })
    return {"item": result, "demo_only": True}


@router.post("/{alert_id}/reopen")
async def reopen_alert(
    alert_id: int,
    payload: ReopenPayload | None = None,
    principal: dict = Depends(require_permission(PERM_ALERTS_RESOLVE)),
):
    reason = payload.reason if payload else None
    try:
        result = transition_alert_state(alert_id, action="reopen", actor=principal["sub"], note=reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    await hub.broadcast({
        "type": "alert.updated",
        "event_id": alert_id,
        "alert": result,
        "action": "reopen",
        "actor": principal["sub"],
        "demo_only": True,
    })
    return {"item": result, "demo_only": True}


@router.post("/{alert_id}/notes")
async def add_alert_note(
    alert_id: int,
    payload: NotePayload,
    principal: dict = Depends(require_permission(PERM_ALERTS_ACKNOWLEDGE)),
):
    try:
        result = transition_alert_state(alert_id, action="add_note", actor=principal["sub"], note=payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    await hub.broadcast({
        "type": "alert.updated",
        "event_id": alert_id,
        "alert": result,
        "action": "note_added",
        "actor": principal["sub"],
        "demo_only": True,
    })
    return {"item": result, "demo_only": True}


@router.get("/{alert_id}/audit")
def get_alert_audit(
    alert_id: int,
    principal: dict = Depends(require_permission(PERM_AUDIT_READ)),
):
    items = list_alert_audit(alert_id)
    if not items:
        if not any(item["id"] == alert_id for item in list_alerts(limit=100)):
            raise HTTPException(status_code=404, detail="Alert not found")
    return {"items": items, "count": len(items), "demo_only": True}
