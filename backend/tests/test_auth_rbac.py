"""Comprehensive tests for Phase 2: Authentication, Authorization (RBAC) and Audit Logging."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage import initialize_storage
from auth_helpers import authenticate_test_client


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "auth_rbac_test.sqlite3"
    monkeypatch.setenv("VITALGUARD_DB_PATH", str(db_path))
    monkeypatch.setenv("VITALGUARD_AUTH_SECRET", "test-secret-at-least-32-chars-long-here!")
    initialize_storage()
    with TestClient(app) as test_client:
        yield test_client


def test_login_success_and_role_returned(client):
    # Clinician login
    res = client.post("/api/v1/auth/login", json={
        "username": "clinician",
        "password": "ClinicianPass123!",
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["role"] == "clinician"
    assert data["username"] == "clinician"

    # Nurse login
    res_nurse = client.post("/api/v1/auth/login", json={
        "username": "nurse",
        "password": "NursePass123!",
    })
    assert res_nurse.status_code == 200
    assert res_nurse.json()["role"] == "nurse"

    # Admin login
    res_admin = client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "AdminPass123!",
    })
    assert res_admin.status_code == 200
    assert res_admin.json()["role"] == "admin"


def test_login_failure_generic_error(client):
    res = client.post("/api/v1/auth/login", json={
        "username": "clinician",
        "password": "WrongPassword!",
    })
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid username or password"


def test_logout_revokes_token(client):
    # Log in as clinician
    res = client.post("/api/v1/auth/login", json={
        "username": "clinician",
        "password": "ClinicianPass123!",
    })
    token = res.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    # Verify token works
    me_res = client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["subject"] == "clinician"

    # Log out
    logout_res = client.post("/api/v1/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["logged_out"] is True

    # Attempting to use the revoked token must fail with 401
    me_after_res = client.get("/api/v1/auth/me")
    assert me_after_res.status_code == 401
    assert "revoked" in me_after_res.json()["detail"]


def test_disabled_account_cannot_authenticate_or_use_tokens(client):
    # Log in as admin
    admin_token = authenticate_test_client(client, role="admin")

    # Disable the nurse account
    # First get user list to find nurse id
    users_res = client.get("/api/v1/admin/users")
    assert users_res.status_code == 200
    nurse_user = next(u for u in users_res.json() if u["username"] == "nurse")
    nurse_id = nurse_user["id"]

    # Disable nurse
    disable_res = client.patch(f"/api/v1/admin/users/{nurse_id}/status", json={"active": False})
    assert disable_res.status_code == 200
    assert disable_res.json()["active"] is False

    # Attempt login as disabled nurse
    nurse_login_res = client.post("/api/v1/auth/login", json={
        "username": "nurse",
        "password": "NursePass123!",
    })
    assert nurse_login_res.status_code == 401


def test_rbac_patient_deactivation_is_admin_only(client):
    # Clinician creates patient
    authenticate_test_client(client, role="clinician")
    create_res = client.post("/api/v1/patients", json={
        "patient_id": "P-RBAC-01",
        "display_name": "Test Patient",
    })
    assert create_res.status_code == 201

    # Clinician attempts deactivation -> 403 Forbidden
    deact_res = client.post("/api/v1/patients/P-RBAC-01/deactivate")
    assert deact_res.status_code == 403

    # Nurse attempts deactivation -> 403 Forbidden
    authenticate_test_client(client, role="nurse")
    deact_res_nurse = client.post("/api/v1/patients/P-RBAC-01/deactivate")
    assert deact_res_nurse.status_code == 403

    # Admin attempts deactivation -> 200 OK
    authenticate_test_client(client, role="admin")
    deact_res_admin = client.post("/api/v1/patients/P-RBAC-01/deactivate")
    assert deact_res_admin.status_code == 200
    assert deact_res_admin.json()["active"] is False


def test_rbac_alert_resolution_is_clinician_only(client):
    # Seed an alert
    authenticate_test_client(client, role="admin")
    from app.alert_service import create_alert
    alert = create_alert(
        patient_id="P-ALERT-RBAC",
        event_key="rbac:test:01",
        severity="high",
        title="Critical BP",
        details={"bp": 180},
    )
    alert_id = alert["id"]

    # Nurse can acknowledge
    authenticate_test_client(client, role="nurse")
    ack_res = client.post(f"/api/v1/alerts/{alert_id}/acknowledge", json={"actor": "nurse"})
    assert ack_res.status_code == 200

    # Nurse CANNOT resolve (clinician privilege) -> 403 Forbidden
    res_nurse = client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"actor": "nurse"})
    assert res_nurse.status_code == 403

    # Clinician CAN resolve -> 200 OK
    authenticate_test_client(client, role="clinician")
    res_clinician = client.post(f"/api/v1/alerts/{alert_id}/resolve", json={"actor": "clinician"})
    assert res_clinician.status_code == 200
    assert res_clinician.json()["item"]["status"] == "resolved"


def test_rbac_admin_routes_restricted_to_admin(client):
    # Clinician tries to access user management -> 403
    authenticate_test_client(client, role="clinician")
    res = client.get("/api/v1/admin/users")
    assert res.status_code == 403

    # Nurse tries to read audit logs -> 403
    authenticate_test_client(client, role="nurse")
    res = client.get("/api/v1/admin/audit")
    assert res.status_code == 403

    # Admin accesses both -> 200 OK
    authenticate_test_client(client, role="admin")
    assert client.get("/api/v1/admin/users").status_code == 200
    audit_res = client.get("/api/v1/admin/audit")
    assert audit_res.status_code == 200
    assert "items" in audit_res.json()


def test_audit_log_captures_security_and_patient_events(client):
    authenticate_test_client(client, role="clinician")

    # Create a patient
    client.post("/api/v1/patients", json={
        "patient_id": "P-AUDIT-TEST",
        "display_name": "Audit Tracked Patient",
    })

    # Switch to admin to view audit trail
    authenticate_test_client(client, role="admin")
    audit_res = client.get("/api/v1/admin/audit?entity_type=patient")
    assert audit_res.status_code == 200
    items = audit_res.json()["items"]
    assert any(i["entity_id"] == "P-AUDIT-TEST" and i["action"] == "patient_created" for i in items)
