"""
Municipal Role-Based Access Control and Authorization Test Suite
================================================================
Verifies that municipal endpoints enforce strict role boundaries:
- Citizens cannot access municipal operations endpoints (403 Forbidden).
- Unauthenticated requests are rejected (401 Unauthorized).
- Municipal officers can access triage, inspection, and resolution.
- Department admins can route incidents and assign officers.
- Municipal admins can manage departments and onboard personnel.
"""

import uuid
import pytest
from backend.db.engine import get_session_factory
from backend.db.models import User
from backend.auth import generate_auth_token


def create_user_with_role(client, role: str):
    email = f"user_{uuid.uuid4().hex[:6]}@civiclens.gov.in"
    res = client.post("/api/v1/auth/register", json={
        "display_name": f"Test {role}",
        "email": email,
        "password": "Password123",
        "confirm_password": "Password123"
    })
    user_id = res.get_json()["user"]["id"]

    db = get_session_factory()()
    u = db.query(User).filter_by(id=user_id).one()
    u.role = role
    db.commit()
    db.close()

    token = generate_auth_token(user_id, role)
    return token, user_id


def test_unauthenticated_requests_rejected(client):
    """Endpoints reject requests without credentials."""
    res = client.get("/api/v2/municipal/metrics")
    assert res.status_code == 401

    res = client.get("/api/v2/municipal/departments")
    assert res.status_code == 401

    res = client.get("/api/v2/municipal/incidents")
    assert res.status_code == 401


def test_citizen_forbidden_from_municipal_endpoints(client):
    """Citizens cannot access internal municipal APIs."""
    cit_token, _ = create_user_with_role(client, "citizen")
    headers = {"Authorization": f"Bearer {cit_token}"}

    res = client.get("/api/v2/municipal/metrics", headers=headers)
    assert res.status_code == 403

    res = client.get("/api/v2/municipal/departments", headers=headers)
    assert res.status_code == 403

    res = client.get("/api/v2/municipal/incidents", headers=headers)
    assert res.status_code == 403

    res = client.post("/api/v2/municipal/departments", json={"name": "Test"}, headers=headers)
    assert res.status_code == 403


def test_municipal_officer_permissions(client):
    """Field officers can access triage and metrics, but cannot create departments."""
    off_token, _ = create_user_with_role(client, "municipal_officer")
    headers = {"Authorization": f"Bearer {off_token}"}

    # Allowed
    res = client.get("/api/v2/municipal/metrics", headers=headers)
    assert res.status_code == 200

    res = client.get("/api/v2/municipal/incidents", headers=headers)
    assert res.status_code == 200

    res = client.get("/api/v2/municipal/departments", headers=headers)
    assert res.status_code == 200

    # Denied: department creation
    res = client.post("/api/v2/municipal/departments", json={"name": "New Dept", "code": "NEW_DEPT"}, headers=headers)
    assert res.status_code == 403


def test_dept_admin_permissions(client):
    """Dept admin can view officers and assign, but cannot onboard officers."""
    da_token, _ = create_user_with_role(client, "dept_admin")
    headers = {"Authorization": f"Bearer {da_token}"}

    res = client.get("/api/v2/municipal/officers", headers=headers)
    assert res.status_code == 200

    res = client.post("/api/v2/municipal/officers/onboard", json={
        "display_name": "New Officer",
        "email": "new.off@civiclens.gov.in",
        "password": "Password123",
        "role": "municipal_officer"
    }, headers=headers)
    assert res.status_code == 403


def test_municipal_admin_full_permissions(client):
    """Municipal admin can access everything, create departments, and onboard officers."""
    ma_token, _ = create_user_with_role(client, "municipal_admin")
    headers = {"Authorization": f"Bearer {ma_token}"}

    res = client.get("/api/v2/municipal/metrics", headers=headers)
    assert res.status_code == 200

    code = f"DEPT_{uuid.uuid4().hex[:5].upper()}"
    res = client.post("/api/v2/municipal/departments", json={
        "name": f"Department {code}",
        "code": code,
        "description": "Test department"
    }, headers=headers)
    assert res.status_code == 201
    assert res.get_json()["code"] == code

    off_email = f"officer_{uuid.uuid4().hex[:6]}@civiclens.gov.in"
    res = client.post("/api/v2/municipal/officers/onboard", json={
        "display_name": "Field Inspector Roy",
        "email": off_email,
        "password": "Password123",
        "role": "municipal_officer"
    }, headers=headers)
    assert res.status_code == 201
    assert res.get_json()["email"] == off_email
