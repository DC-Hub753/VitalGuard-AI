"""Administrative endpoints for user management and audit log inspection."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError

from .audit_service import list_audit_events, record_audit_event
from .auth import authenticate_principal, require_permission
from .permissions import PERM_AUDIT_READ, PERM_USERS_MANAGE
from .user_schemas import UserCreate, UserResponse, UserRoleUpdate, UserStatusUpdate
from .user_service import (
    create_user,
    get_user_by_id,
    list_users,
    update_user_role,
    update_user_status,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users", response_model=list[UserResponse])
def get_users(
    principal: dict = Depends(require_permission(PERM_USERS_MANAGE)),
):
    """List all registered system users. Restricted to Admin."""
    return list_users()


@router.post("/users", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def add_user(
    payload: UserCreate,
    principal: dict = Depends(require_permission(PERM_USERS_MANAGE)),
):
    """Create a new authorized account. Restricted to Admin."""
    try:
        user = create_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
            full_name=payload.full_name,
        )
        record_audit_event(
            entity_type="user",
            entity_id=str(user["id"]),
            action="user_created",
            actor=principal["sub"],
            details={"username": payload.username, "role": payload.role},
        )
        return user
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this username already exists",
        )


@router.patch("/users/{user_id}/status", response_model=UserResponse)
def set_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    principal: dict = Depends(require_permission(PERM_USERS_MANAGE)),
):
    """Enable or disable a user account. Restricted to Admin."""
    user = update_user_status(user_id, active=payload.active)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    record_audit_event(
        entity_type="user",
        entity_id=str(user_id),
        action="user_status_changed",
        actor=principal["sub"],
        details={"username": user["username"], "active": payload.active},
    )
    return user


@router.patch("/users/{user_id}/role", response_model=UserResponse)
def set_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    principal: dict = Depends(require_permission(PERM_USERS_MANAGE)),
):
    """Change role of a user account. Restricted to Admin."""
    user = update_user_role(user_id, role=payload.role)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    record_audit_event(
        entity_type="user",
        entity_id=str(user_id),
        action="user_role_changed",
        actor=principal["sub"],
        details={"username": user["username"], "new_role": payload.role},
    )
    return user


@router.get("/audit")
def get_audit_trail(
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: dict = Depends(require_permission(PERM_AUDIT_READ)),
):
    """Query immutable audit events. Restricted to Admin."""
    items = list_audit_events(
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )
    return {
        "items": items,
        "count": len(items),
        "limit": limit,
        "offset": offset,
        "demo_only": True,
    }
