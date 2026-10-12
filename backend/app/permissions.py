"""Explicit Role-Based Access Control (RBAC) definitions and permissions matrix.

Roles:
- admin: Manage authorized user accounts, review audit logs, and system operations.
- clinician: Access authorized patient records, review risk assessments/explanations,
             manage clinical alerts (acknowledge/resolve/assign), run news2 calculations.
- nurse: Access authorized patient records, submit/review observations, acknowledge alerts.
"""
from typing import Literal

Role = Literal["admin", "clinician", "nurse"]

VALID_ROLES: set[Role] = {"admin", "clinician", "nurse"}

# Granular Permission Strings
PERM_USERS_MANAGE = "users:manage"
PERM_AUDIT_READ = "audit:read"
PERM_PATIENTS_READ = "patients:read"
PERM_PATIENTS_WRITE = "patients:write"
PERM_PATIENTS_DEACTIVATE = "patients:deactivate"
PERM_OBSERVATIONS_READ = "observations:read"
PERM_OBSERVATIONS_CREATE = "observations:create"
PERM_RISK_PREDICT = "risk:predict"
PERM_RISK_EXPLAIN = "risk:explain"
PERM_NEWS2_CALCULATE = "news2:calculate"
PERM_ALERTS_READ = "alerts:read"
PERM_ALERTS_ACKNOWLEDGE = "alerts:acknowledge"
PERM_ALERTS_RESOLVE = "alerts:resolve"
PERM_LIVE_SUBSCRIBE = "live:subscribe"
PERM_OPS_METRICS = "ops:metrics"

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    "admin": {
        PERM_USERS_MANAGE,
        PERM_AUDIT_READ,
        PERM_PATIENTS_READ,
        PERM_PATIENTS_WRITE,
        PERM_PATIENTS_DEACTIVATE,
        PERM_OBSERVATIONS_READ,
        PERM_OBSERVATIONS_CREATE,
        PERM_RISK_PREDICT,
        PERM_RISK_EXPLAIN,
        PERM_NEWS2_CALCULATE,
        PERM_ALERTS_READ,
        PERM_ALERTS_ACKNOWLEDGE,
        PERM_ALERTS_RESOLVE,
        PERM_LIVE_SUBSCRIBE,
        PERM_OPS_METRICS,
    },
    "clinician": {
        PERM_PATIENTS_READ,
        PERM_PATIENTS_WRITE,
        PERM_OBSERVATIONS_READ,
        PERM_OBSERVATIONS_CREATE,
        PERM_RISK_PREDICT,
        PERM_RISK_EXPLAIN,
        PERM_NEWS2_CALCULATE,
        PERM_ALERTS_READ,
        PERM_ALERTS_ACKNOWLEDGE,
        PERM_ALERTS_RESOLVE,
        PERM_LIVE_SUBSCRIBE,
    },
    "nurse": {
        PERM_PATIENTS_READ,
        PERM_PATIENTS_WRITE,
        PERM_OBSERVATIONS_READ,
        PERM_OBSERVATIONS_CREATE,
        PERM_RISK_PREDICT,
        PERM_NEWS2_CALCULATE,
        PERM_ALERTS_READ,
        PERM_ALERTS_ACKNOWLEDGE,
        PERM_LIVE_SUBSCRIBE,
    },
}


def role_has_permission(role: str, permission: str) -> bool:
    """Return True if the role possesses the required permission."""
    return permission in ROLE_PERMISSIONS.get(role, set())  # type: ignore[arg-type]
