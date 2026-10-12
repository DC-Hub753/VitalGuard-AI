"""HTTP endpoints for patient CRUD; all routes require authentication and RBAC permissions."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError

from .audit_service import record_audit_event
from .auth import authenticate_principal, require_permission
from .patient_schemas import PatientCreate, PatientResponse, PatientUpdate
from .patient_service import (
    create_patient,
    deactivate_patient,
    get_patient,
    list_patients,
    update_patient,
)
from .permissions import (
    PERM_PATIENTS_DEACTIVATE,
    PERM_PATIENTS_READ,
    PERM_PATIENTS_WRITE,
)

router = APIRouter(
    prefix="/api/v1/patients",
    tags=["patients"],
    dependencies=[Depends(authenticate_principal)],
)


@router.get("")
def get_patients(
    ward: str | None = Query(default=None, min_length=1, max_length=80),
    active_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: dict = Depends(require_permission(PERM_PATIENTS_READ)),
):
    """List patients with optional ward filter and pagination."""
    items, total = list_patients(
        active_only=active_only, ward=ward, limit=limit, offset=offset
    )
    return {
        "items": items,
        "count": len(items),
        "total": total,
        "limit": limit,
        "offset": offset,
        "demo_only": True,
    }


@router.post("", status_code=201, response_model=PatientResponse)
def create_new_patient(
    payload: PatientCreate,
    principal: dict = Depends(require_permission(PERM_PATIENTS_WRITE)),
):
    """Create a new patient record. Returns 409 if the patient_id already exists."""
    try:
        patient = create_patient(
            patient_id=payload.patient_id,
            display_name=payload.display_name,
            sex=payload.sex,
            date_of_birth=payload.date_of_birth,
            ward=payload.ward,
            bed=payload.bed,
            created_by=principal["sub"],
        )
        record_audit_event(
            entity_type="patient",
            entity_id=payload.patient_id,
            action="patient_created",
            actor=principal["sub"],
            details={"ward": payload.ward, "display_name": payload.display_name},
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="A patient with this ID already exists")
    return patient


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient_by_id(
    patient_id: str,
    principal: dict = Depends(require_permission(PERM_PATIENTS_READ)),
):
    """Return a single patient by ID. Returns 404 if not found or inactive."""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.patch("/{patient_id}", response_model=PatientResponse)
def update_patient_by_id(
    patient_id: str,
    payload: PatientUpdate,
    principal: dict = Depends(require_permission(PERM_PATIENTS_WRITE)),
):
    """Partial update of a patient record. Returns 404 if not found or inactive."""
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        patient = get_patient(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        return patient
    patient = update_patient(patient_id, updates=updates)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    record_audit_event(
        entity_type="patient",
        entity_id=patient_id,
        action="patient_updated",
        actor=principal["sub"],
        details={"fields": list(updates.keys())},
    )
    return patient


@router.post("/{patient_id}/deactivate", response_model=PatientResponse)
def deactivate_patient_by_id(
    patient_id: str,
    principal: dict = Depends(require_permission(PERM_PATIENTS_DEACTIVATE)),
):
    """Soft-delete a patient. Preserves historical data. Restricted to Admin."""
    patient = deactivate_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    record_audit_event(
        entity_type="patient",
        entity_id=patient_id,
        action="patient_deactivated",
        actor=principal["sub"],
        details={"active": False},
    )
    return patient
