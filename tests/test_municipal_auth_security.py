"""
CivicLens Municipal Authentication, Security & Workflow Test Suite
==================================================================
Tests for municipal official authentication, rate limiting, role enforcement,
invitation lifecycle, incident state machine extensions, and CSRF protection.
"""

import uuid
import pytest
from werkzeug.security import generate_password_hash

from backend.db.engine import get_session_factory
from backend.db.models import User, Incident, OfficialInvitation
from backend.auth import generate_auth_token
from backend.services.incident_state_machine_service import IncidentStateMachineService, IncidentStatus


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def create_official_user(role="municipal_officer", is_active=True, password="OfficialPass123!"):
    """Helper to create an official in the test database."""
    SessionFactory = get_session_factory()
    db = SessionFactory()
    user_id = str(uuid.uuid4())
    email = f"officer_{uuid.uuid4().hex[:6]}@bbmp.gov.in"
    u = User(
        id=user_id,
        display_name=f"Official {role}",
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        is_active=is_active,
        preferred_language="en"
    )
    db.add(u)
    db.commit()
    db.close()
    return {"id": user_id, "email": email, "password": password, "role": role}


def create_citizen(password="CitizenPass123!"):
    """Helper to create a citizen in the test database."""
    SessionFactory = get_session_factory()
    db = SessionFactory()
    user_id = str(uuid.uuid4())
    email = f"citizen_{uuid.uuid4().hex[:6]}@example.com"
    u = User(
        id=user_id,
        display_name="Citizen User",
        email=email,
        password_hash=generate_password_hash(password),
        role="citizen",
        is_active=True,
        preferred_language="en"
    )
    db.add(u)
    db.commit()
    db.close()
    return {"id": user_id, "email": email, "password": password, "role": "citizen"}


# ---------------------------------------------------------------------------
# Municipal Official Login Tests
# ---------------------------------------------------------------------------

class TestMunicipalOfficialLogin:
    def test_valid_municipal_login(self, client):
        """Valid municipal credentials return 200 with session token and role."""
        officer = create_official_user(role="municipal_officer")
        res = client.post("/api/v1/auth/official-login", json={
            "email": officer["email"],
            "password": officer["password"]
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert "token" in data
        assert data["user"]["role"] == "municipal_officer"

    def test_invalid_password_rejected(self, client):
        """Invalid official password returns 400 error."""
        officer = create_official_user(role="municipal_officer")
        res = client.post("/api/v1/auth/official-login", json={
            "email": officer["email"],
            "password": "WrongPassword999!"
        })
        assert res.status_code == 400
        data = res.get_json()
        assert "error" in data or "message" in data

    def test_citizen_cannot_use_official_login(self, client):
        """Citizen accounts attempting official login are rejected."""
        cit = create_citizen()
        res = client.post("/api/v1/auth/official-login", json={
            "email": cit["email"],
            "password": cit["password"]
        })
        # Must return 401 or 400 with unauthorized message
        assert res.status_code in (400, 401, 403)
        data = res.get_json()
        assert "error" in data or "message" in data

    def test_suspended_account_rejected(self, client):
        """Deactivated/suspended official account cannot log in."""
        suspended = create_official_user(role="municipal_officer", is_active=False)
        res = client.post("/api/v1/auth/official-login", json={
            "email": suspended["email"],
            "password": suspended["password"]
        })
        assert res.status_code in (400, 403)

    def test_empty_credentials_rejected(self, client):
        """Empty credentials return 400."""
        res = client.post("/api/v1/auth/official-login", json={})
        assert res.status_code == 400

    def test_nonexistent_email_rejected(self, client):
        """Non-existent email returns 400 without revealing account existence."""
        res = client.post("/api/v1/auth/official-login", json={
            "email": "ghost.user@civiclens.test",
            "password": "AnyPassword123"
        })
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# State Machine Lifecycle & New States Tests
# ---------------------------------------------------------------------------

class TestIncidentStateMachineLifecycle:
    def test_needs_more_information_state(self):
        """NEEDS_MORE_INFORMATION is in IncidentStatus and transitions from AWAITING_VERIFICATION."""
        assert hasattr(IncidentStatus, "NEEDS_MORE_INFORMATION")
        assert IncidentStatus.NEEDS_MORE_INFORMATION == "needs_more_information"
        assert IncidentStatus.NEEDS_MORE_INFORMATION in IncidentStatus.ALL

        svc = IncidentStateMachineService()
        ok, _ = svc.can_transition(
            IncidentStatus.AWAITING_VERIFICATION,
            IncidentStatus.NEEDS_MORE_INFORMATION,
            user_role="municipal_admin"
        )
        assert ok is True

    def test_reopened_state(self):
        """REOPENED is in IncidentStatus and transitions from RESOLVED."""
        assert hasattr(IncidentStatus, "REOPENED")
        assert IncidentStatus.REOPENED == "reopened"
        assert IncidentStatus.REOPENED in IncidentStatus.ALL

        svc = IncidentStateMachineService()
        ok, _ = svc.can_transition(
            IncidentStatus.RESOLVED,
            IncidentStatus.REOPENED,
            user_role="municipal_admin"
        )
        assert ok is True

    def test_citizen_cannot_modify_status(self):
        """Citizen role cannot trigger any state machine transition."""
        svc = IncidentStateMachineService()
        ok, err = svc.can_transition(
            IncidentStatus.NEW,
            IncidentStatus.AWAITING_VERIFICATION,
            user_role="citizen"
        )
        assert ok is False
        assert "Citizens cannot modify" in (err or "")

    def test_officer_cannot_close_incident(self):
        """Municipal officer cannot unilaterally close canonical incidents."""
        svc = IncidentStateMachineService()
        ok, err = svc.can_transition(
            IncidentStatus.RESOLVED,
            IncidentStatus.CLOSED,
            user_role="municipal_officer",
            is_assigned_officer=True
        )
        assert ok is False
        assert "cannot close" in (err or "")


# ---------------------------------------------------------------------------
# CSRF and Route Tests
# ---------------------------------------------------------------------------

class TestCSRFAndRoutes:
    def test_csrf_token_endpoint(self, client):
        """GET /api/v1/auth/csrf-token returns 200 with token and sets cookie."""
        res = client.get("/api/v1/auth/csrf-token")
        assert res.status_code == 200
        data = res.get_json()
        assert "csrf_token" in data
        assert len(data["csrf_token"]) >= 32
        assert "cl_csrf_token" in res.headers.get("Set-Cookie", "")

    def test_municipal_login_html_route(self, client):
        """GET /municipal-login.html and /frontend/municipal-login.html return 200."""
        res = client.get("/municipal-login.html")
        assert res.status_code == 200
        assert b"Municipal Official" in res.data or b"Official Sign In" in res.data

        res2 = client.get("/frontend/municipal-login.html")
        assert res2.status_code == 200

    def test_public_statistics_includes_required_keys(self, client):
        """GET /api/v2/public/statistics returns all required database metrics."""
        res = client.get("/api/v2/public/statistics")
        assert res.status_code == 200
        data = res.get_json()
        assert "total_canonical_incidents" in data
        assert "total_citizen_reports" in data
        assert "deduplication_ratio" in data
        assert "status_breakdown" in data
