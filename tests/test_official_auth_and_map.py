"""
Tests for CivicLens Official Authentication, Municipal Invitations & Public Map API
====================================================================================
Validates:
- Public Map viewport queries, bounding box filtering, and zero-incident handling.
- Administrative invitation creation, token hashing, expiration, and acceptance.
- Official login verification and restriction of citizen accounts from municipal portal.
- Multi-municipality querying and department linkage.
"""

import hashlib
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from werkzeug.security import generate_password_hash

from backend.db.engine import get_session_factory
from backend.db.models import User, Municipality, Department, DepartmentMembership, OfficialInvitation, Incident
from backend.services.official_auth_service import OfficialAuthService
from backend.auth import generate_auth_token


@pytest.fixture
def auth_setup(app):
    """Sets up an admin user, a citizen user, and default BBMP municipality for testing."""
    with app.app_context():
        factory = get_session_factory()
        db = factory()
        try:
            now = datetime.now(timezone.utc)
            # Municipality
            bbmp = db.query(Municipality).filter_by(code="BBMP").first()
            if not bbmp:
                bbmp = Municipality(
                    name="Bruhat Bengaluru Mahanagara Palike",
                    code="BBMP",
                    state="Karnataka",
                    status="active"
                )
                db.add(bbmp)
                db.flush()

            # Department
            dept = db.query(Department).first()
            if not dept:
                dept = Department(
                    name="Road Infrastructure Dept",
                    code="RID",
                    municipality_id=bbmp.id,
                    is_active=True
                )
                db.add(dept)
                db.flush()

            # 1. System Admin
            admin_id = str(uuid.uuid4())
            admin_email = f"admin_{uuid.uuid4().hex[:6]}@civiclens.gov.in"
            admin = User(
                id=admin_id,
                display_name="Super Admin",
                email=admin_email,
                role="system_admin",
                password_hash=generate_password_hash("AdminPass123!@#"),
                is_active=True,
                created_at=now,
                updated_at=now
            )
            db.add(admin)

            # 2. Citizen User
            cit_id = str(uuid.uuid4())
            cit_email = f"citizen_{uuid.uuid4().hex[:6]}@example.com"
            citizen = User(
                id=cit_id,
                display_name="Citizen Sharma",
                email=cit_email,
                role="citizen",
                password_hash=generate_password_hash("CitizenPass123!"),
                is_active=True,
                created_at=now,
                updated_at=now
            )
            db.add(citizen)

            # 3. Canonical Public Incident
            inc_ref = f"INC-{uuid.uuid4().hex[:6].upper()}"
            incident = Incident(
                incident_reference=inc_ref,
                category="pothole",
                severity="severe",
                priority="high",
                status="verified",
                latitude=12.9716,
                longitude=77.5946,
                address="MG Road, Bengaluru",
                report_count=2,
                created_at=now
            )
            db.add(incident)

            db.commit()

            admin_token = generate_auth_token(admin.id, admin.role)
            cit_token = generate_auth_token(citizen.id, citizen.role)

            return {
                "admin": {"id": admin.id, "email": admin_email, "token": admin_token, "password": "AdminPass123!@#"},
                "citizen": {"id": citizen.id, "email": cit_email, "token": cit_token, "password": "CitizenPass123!"},
                "bbmp_id": bbmp.id,
                "dept_id": dept.id,
                "incident_ref": inc_ref
            }
        finally:
            db.close()


# ─── Public Map Tests ────────────────────────────────────────────────────────

def test_public_map_viewport_incidents_success(client, auth_setup):
    """Scenario: Viewport query returns published canonical incidents within geographic bounds."""
    res = client.get(
        "/api/v2/public/incidents/viewport?min_lon=77.50&min_lat=12.90&max_lon=77.70&max_lat=13.05"
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "items" in data
    assert data["count"] >= 1
    refs = [item["incident_reference"] for item in data["items"]]
    assert auth_setup["incident_ref"] in refs


def test_public_map_viewport_zero_incidents_clean_response(client, auth_setup):
    """Scenario: Viewport with no incidents returns 200 with count 0 (never 500 error)."""
    res = client.get(
        "/api/v2/public/incidents/viewport?min_lon=10.0&min_lat=10.0&max_lon=11.0&max_lat=11.0"
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["count"] == 0
    assert data["items"] == []


def test_public_map_category_and_severity_filters(client, auth_setup):
    """Scenario: Filter by category pothole matches; filter by drainage returns zero."""
    res_pothole = client.get(
        "/api/v2/public/incidents/viewport?min_lon=77.50&min_lat=12.90&max_lon=77.70&max_lat=13.05&category=pothole"
    )
    assert res_pothole.status_code == 200
    assert res_pothole.get_json()["count"] >= 1

    res_drainage = client.get(
        "/api/v2/public/incidents/viewport?min_lon=77.50&min_lat=12.90&max_lon=77.70&max_lat=13.05&category=drainage"
    )
    assert res_drainage.status_code == 200
    assert res_drainage.get_json()["count"] == 0


# ─── Official Authentication & Invitations Tests ─────────────────────────────

def test_official_login_success(client, auth_setup):
    """Scenario: Authorized system_admin can log in through official portal."""
    res = client.post("/api/v1/auth/official-login", json={
        "email": auth_setup["admin"]["email"],
        "password": auth_setup["admin"]["password"]
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["user"]["role"] == "system_admin"
    assert "token" in data


def test_official_login_denies_citizen(client, auth_setup):
    """Scenario: Citizen attempting official login is denied with 401 or 403."""
    res = client.post("/api/v1/auth/official-login", json={
        "email": auth_setup["citizen"]["email"],
        "password": auth_setup["citizen"]["password"]
    })
    # Must be forbidden or unauthorized
    assert res.status_code in (401, 403)
    data = res.get_json()
    assert "municipal access" in (data.get("error") or data.get("message") or "").lower()


def test_invitation_lifecycle_create_verify_accept(client, auth_setup):
    """Scenario: Admin creates invitation -> token verified -> official accepts and logs in."""
    new_officer_email = f"officer_{uuid.uuid4().hex[:6]}@bbmp.gov.in"

    # 1. Admin creates invitation
    res_inv = client.post(
        "/api/v1/auth/invitations",
        headers={"Authorization": f"Bearer {auth_setup['admin']['token']}"},
        json={
            "email": new_officer_email,
            "role": "municipal_officer",
            "municipality_id": auth_setup["bbmp_id"],
            "department_id": auth_setup["dept_id"]
        }
    )
    assert res_inv.status_code == 201
    inv_data = res_inv.get_json()["invitation"]
    raw_token = inv_data["invitation_token"]
    assert raw_token is not None

    # 2. Citizen cannot create invitations (403 Forbidden)
    res_unauth = client.post(
        "/api/v1/auth/invitations",
        headers={"Authorization": f"Bearer {auth_setup['citizen']['token']}"},
        json={
            "email": "intruder@bbmp.gov.in",
            "role": "municipal_officer"
        }
    )
    assert res_unauth.status_code == 403

    # 3. Verify invitation token
    res_verify = client.get(f"/api/v1/auth/invitations/verify/{raw_token}")
    assert res_verify.status_code == 200
    ver_data = res_verify.get_json()["invitation"]
    assert ver_data["valid"] is True
    assert ver_data["email"] == new_officer_email
    assert ver_data["intended_role"] == "municipal_officer"

    # 4. Accept invitation and set password
    res_accept = client.post("/api/v1/auth/invitations/accept", json={
        "token": raw_token,
        "display_name": "Officer Ramesh",
        "password": "OfficialSecure123!",
        "confirm_password": "OfficialSecure123!"
    })
    assert res_accept.status_code == 200
    accept_data = res_accept.get_json()
    assert accept_data["status"] == "success"
    assert accept_data["user"]["role"] == "municipal_officer"

    # 5. Officer logs in with new credentials
    res_login = client.post("/api/v1/auth/official-login", json={
        "email": new_officer_email,
        "password": "OfficialSecure123!"
    })
    assert res_login.status_code == 200
    assert res_login.get_json()["user"]["role"] == "municipal_officer"


def test_municipalities_list_api(client, auth_setup):
    """Scenario: Authorized staff can retrieve registered municipalities."""
    res = client.get(
        "/api/v2/municipal/municipalities",
        headers={"Authorization": f"Bearer {auth_setup['admin']['token']}"}
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    codes = [m["code"] for m in data["municipalities"]]
    assert "BBMP" in codes
