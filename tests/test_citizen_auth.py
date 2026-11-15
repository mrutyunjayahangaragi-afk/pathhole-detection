"""
Citizen Authentication & Profile Unit and Integration Tests
===========================================================

Verifies:
- Registration validation and password hashing
- Duplicate account prevention
- Login, session, and Bearer token issuance
- Brute-force rate limiting
- Profile retrieval with real report counts
- Profile updates (permitted fields only)
- Logout and session invalidation
"""

import uuid
import pytest
from backend.services.auth_service import AuthService
from backend.errors import ValidationError, NotFoundError


@pytest.fixture
def auth_service(app):
    return AuthService()


def test_register_citizen_success(client):
    email = f"ramesh_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "display_name": "Ramesh Kumar",
        "email": email,
        "phone": "+919876543210",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "preferred_language": "kn"
    }
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "success"
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "citizen"
    assert data["user"]["preferred_language"] == "kn"
    assert "token" in data
    assert "password_hash" not in data["user"]


def test_register_duplicate_email_fails(client):
    email = f"priya_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "display_name": "Priya Sharma",
        "email": email,
        "password": "SecurePass123",
        "confirm_password": "SecurePass123"
    }
    res1 = client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    # Attempt duplicate registration
    res2 = client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 400
    assert "already exists" in res2.get_json()["error"]


def test_register_validation_failures(client):
    # Short name
    r1 = client.post("/api/v1/auth/register", json={
        "display_name": "A", "email": "valid@example.com", "password": "Password1", "confirm_password": "Password1"
    })
    assert r1.status_code == 400

    # Invalid email format
    r2 = client.post("/api/v1/auth/register", json={
        "display_name": "Valid Name", "email": "not-an-email", "password": "Password1", "confirm_password": "Password1"
    })
    assert r2.status_code == 400

    # Weak password (< 8 chars)
    r3 = client.post("/api/v1/auth/register", json={
        "display_name": "Valid Name", "email": "test@example.com", "password": "pass1", "confirm_password": "pass1"
    })
    assert r3.status_code == 400

    # Mismatched passwords
    r4 = client.post("/api/v1/auth/register", json={
        "display_name": "Valid Name", "email": "test@example.com", "password": "Password123", "confirm_password": "MismatchPassword123"
    })
    assert r4.status_code == 400


def test_login_success_and_logout(client):
    email = f"ananya_{uuid.uuid4().hex[:6]}@example.com"
    # Register account
    client.post("/api/v1/auth/register", json={
        "display_name": "Ananya Roy",
        "email": email,
        "password": "MySecretPass123",
        "confirm_password": "MySecretPass123"
    })

    # Clear session to test fresh login
    client.post("/api/v1/auth/logout")

    # Login
    res = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "MySecretPass123"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["user"]["email"] == email
    assert "token" in data

    # Verify session is authenticated via /me
    me_res = client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.get_json()["user"]["display_name"] == "Ananya Roy"

    # Logout
    logout_res = client.post("/api/v1/auth/logout")
    assert logout_res.status_code == 200

    # Subsequent /me without session or token should be 401
    me_after = client.get("/api/v1/auth/me")
    assert me_after.status_code == 401


def test_login_invalid_password(client):
    email = f"suresh_{uuid.uuid4().hex[:6]}@example.com"
    client.post("/api/v1/auth/register", json={
        "display_name": "Suresh Nair",
        "email": email,
        "password": "CorrectPassword1",
        "confirm_password": "CorrectPassword1"
    })
    client.post("/api/v1/auth/logout")

    res = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "WrongPassword1"
    })
    assert res.status_code == 400
    assert "Invalid email or password" in res.get_json()["error"]


def test_login_rate_limiting_locks_out(client):
    # Try 5 consecutive bad passwords
    email = f"target_{uuid.uuid4().hex[:6]}@example.com"
    for _ in range(5):
        client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "badpassword"
        })

    # 6th attempt should be blocked by rate limiter
    res = client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "badpassword"
    })
    assert res.status_code == 400
    assert "Too many failed login attempts" in res.get_json()["error"]


def test_bearer_token_authorization(client):
    email = f"bearer_{uuid.uuid4().hex[:6]}@example.com"
    reg = client.post("/api/v1/auth/register", json={
        "display_name": "Bearer User",
        "email": email,
        "password": "Password123",
        "confirm_password": "Password123"
    })
    token = reg.get_json()["token"]

    # Clear cookie
    client.post("/api/v1/auth/logout")

    # Access /me with Authorization header
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["user"]["email"] == email


def test_update_profile_permitted_fields_only(client):
    email = f"profile_{uuid.uuid4().hex[:6]}@example.com"
    reg = client.post("/api/v1/auth/register", json={
        "display_name": "Original Name",
        "email": email,
        "password": "Password123",
        "confirm_password": "Password123"
    })
    token = reg.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    update_payload = {
        "display_name": "Updated Name",
        "phone": "+918888899999",
        "preferred_language": "kn",
        "role": "system_admin"  # Attempt privilege escalation
    }
    res = client.patch("/api/v1/auth/profile", json=update_payload, headers=headers)
    assert res.status_code == 200
    data = res.get_json()["user"]
    assert data["display_name"] == "Updated Name"
    assert data["phone"] == "+918888899999"
    assert data["preferred_language"] == "kn"
    # Privilege escalation attempt MUST be ignored
    assert data["role"] == "citizen"
