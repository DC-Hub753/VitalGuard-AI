"""Helpers for exercising authenticated demo API endpoints in tests."""
import os


def authenticate_test_client(client, role: str = "admin") -> str:
    os.environ["VITALGUARD_AUTH_SECRET"] = "test-only-secret-that-is-at-least-32-chars"
    if role == "admin":
        os.environ["VITALGUARD_AUTH_USERNAME"] = "demo-operator"
        os.environ["VITALGUARD_AUTH_PASSWORD"] = "a-long-demo-password"
        response = client.post("/api/v1/auth/login", json={
            "username": "demo-operator",
            "password": "a-long-demo-password",
        })
    elif role == "clinician":
        response = client.post("/api/v1/auth/login", json={
            "username": "clinician",
            "password": "ClinicianPass123!",
        })
    elif role == "nurse":
        response = client.post("/api/v1/auth/login", json={
            "username": "nurse",
            "password": "NursePass123!",
        })
    else:
        raise ValueError(f"Unknown test role: {role}")

    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return token

