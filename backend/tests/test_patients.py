"""Unit and integration tests for Patient CRUD endpoints and persistence."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage import initialize_storage
from auth_helpers import authenticate_test_client


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "patients_test.sqlite3"
    monkeypatch.setenv("VITALGUARD_DB_PATH", str(db_path))
    initialize_storage()
    with TestClient(app) as test_client:
        yield test_client


def test_patients_endpoints_require_authentication(client):
    # Unauthenticated GET
    res = client.get("/api/v1/patients")
    assert res.status_code == 401

    # Unauthenticated POST
    res = client.post("/api/v1/patients", json={
        "patient_id": "P-100",
        "display_name": "Test Patient",
    })
    assert res.status_code == 401

    # Unauthenticated GET by id
    res = client.get("/api/v1/patients/P-100")
    assert res.status_code == 401

    # Unauthenticated PATCH
    res = client.patch("/api/v1/patients/P-100", json={"display_name": "Updated"})
    assert res.status_code == 401

    # Unauthenticated deactivate
    res = client.post("/api/v1/patients/P-100/deactivate")
    assert res.status_code == 401


def test_create_and_get_patient(client):
    authenticate_test_client(client)

    payload = {
        "patient_id": "PATIENT-001",
        "display_name": "Alice Smith",
        "sex": "F",
        "date_of_birth": "1980-05-15",
        "ward": "Cardiology",
        "bed": "C-12",
    }
    res = client.post("/api/v1/patients", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["patient_id"] == "PATIENT-001"
    assert data["display_name"] == "Alice Smith"
    assert data["sex"] == "F"
    assert data["date_of_birth"] == "1980-05-15"
    assert data["ward"] == "Cardiology"
    assert data["bed"] == "C-12"
    assert data["active"] is True
    assert data["demo_only"] is True

    # Retrieve patient by ID
    get_res = client.get("/api/v1/patients/PATIENT-001")
    assert get_res.status_code == 200
    assert get_res.json()["display_name"] == "Alice Smith"


def test_create_duplicate_patient_returns_409(client):
    authenticate_test_client(client)

    payload = {
        "patient_id": "PATIENT-DUP",
        "display_name": "Duplicate Test",
    }
    res = client.post("/api/v1/patients", json=payload)
    assert res.status_code == 201

    dup_res = client.post("/api/v1/patients", json=payload)
    assert dup_res.status_code == 409
    assert "already exists" in dup_res.json()["detail"]


def test_patient_validation_rejects_malformed_inputs(client):
    authenticate_test_client(client)

    # Whitespace in patient_id
    res = client.post("/api/v1/patients", json={
        "patient_id": "PATIENT WITH SPACE",
        "display_name": "Valid Name",
    })
    assert res.status_code == 422

    # Invalid sex code
    res = client.post("/api/v1/patients", json={
        "patient_id": "P-VALID",
        "display_name": "Valid Name",
        "sex": "X",
    })
    assert res.status_code == 422

    # Malformed date of birth
    res = client.post("/api/v1/patients", json={
        "patient_id": "P-VALID",
        "display_name": "Valid Name",
        "date_of_birth": "15-05-1980",
    })
    assert res.status_code == 422

    # Extra fields forbidden
    res = client.post("/api/v1/patients", json={
        "patient_id": "P-VALID",
        "display_name": "Valid Name",
        "unknown_field": "disallowed",
    })
    assert res.status_code == 422


def test_list_patients_filtering_and_pagination(client):
    authenticate_test_client(client)

    # Insert 3 patients across 2 wards
    client.post("/api/v1/patients", json={"patient_id": "P-A", "display_name": "Alice", "ward": "ICU"})
    client.post("/api/v1/patients", json={"patient_id": "P-B", "display_name": "Bob", "ward": "ICU"})
    client.post("/api/v1/patients", json={"patient_id": "P-C", "display_name": "Charlie", "ward": "General"})

    # List all
    res = client.get("/api/v1/patients")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3

    # Filter by ward
    res_ward = client.get("/api/v1/patients?ward=ICU")
    assert res_ward.status_code == 200
    assert res_ward.json()["total"] == 2
    assert all(p["ward"] == "ICU" for p in res_ward.json()["items"])

    # Pagination
    res_page = client.get("/api/v1/patients?limit=2&offset=0")
    assert res_page.status_code == 200
    assert len(res_page.json()["items"]) == 2
    assert res_page.json()["total"] == 3


def test_patch_patient(client):
    authenticate_test_client(client)

    client.post("/api/v1/patients", json={
        "patient_id": "P-UPDATE",
        "display_name": "Original Name",
        "ward": "Ward A",
        "bed": "Bed 1",
    })

    patch_res = client.patch("/api/v1/patients/P-UPDATE", json={
        "display_name": "Updated Name",
        "bed": "Bed 2-B",
    })
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["display_name"] == "Updated Name"
    assert updated["bed"] == "Bed 2-B"
    assert updated["ward"] == "Ward A"  # preserved


def test_deactivate_patient_soft_delete(client):
    authenticate_test_client(client)

    client.post("/api/v1/patients", json={
        "patient_id": "P-DEACT",
        "display_name": "To Deactivate",
    })

    # Deactivate
    deact_res = client.post("/api/v1/patients/P-DEACT/deactivate")
    assert deact_res.status_code == 200
    assert deact_res.json()["active"] is False

    # Once deactivated, get_patient returns 404
    get_res = client.get("/api/v1/patients/P-DEACT")
    assert get_res.status_code == 404

    # Once deactivated, default list_patients excludes it
    list_res = client.get("/api/v1/patients")
    ids = [p["patient_id"] for p in list_res.json()["items"]]
    assert "P-DEACT" not in ids

    # Including inactive returns it
    list_all_res = client.get("/api/v1/patients?active_only=false")
    all_ids = [p["patient_id"] for p in list_all_res.json()["items"]]
    assert "P-DEACT" in all_ids
