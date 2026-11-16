"""
Department and Officer Management Test Suite
============================================
Verifies default department seeding, code uniqueness, deactivation guards,
officer onboarding, department memberships, and live workload calculation.
"""

import uuid
import pytest
from datetime import datetime, timezone

from backend.db.engine import get_session_factory
from backend.db.models import Department, DepartmentMembership, Incident, User
from backend.services.department_management_service import DepartmentManagementService, DEFAULT_DEPARTMENTS
from backend.errors import ValidationError, NotFoundError


@pytest.fixture
def dept_service():
    return DepartmentManagementService()


def test_seed_default_departments(app, dept_service):
    """Ensures core municipal departments exist with codes."""
    dept_service.seed_default_departments()
    depts = dept_service.list_departments(include_inactive=True)

    dept_codes = {d["code"] for d in depts if d["code"]}
    expected_codes = {spec["code"] for spec in DEFAULT_DEPARTMENTS}

    for expected in expected_codes:
        assert expected in dept_codes


def test_department_code_uniqueness(app, dept_service):
    """Attempting to create duplicate department code or name raises ValidationError."""
    code = f"TEST_{uuid.uuid4().hex[:6].upper()}"
    dept_service.create_department(name=f"Unit {code}", code=code)

    with pytest.raises(ValidationError, match="already exists"):
        dept_service.create_department(name=f"Different Name {code}", code=code)


def test_department_deactivation_guard(app, dept_service):
    """Cannot deactivate department while active unresolved incidents exist."""
    code = f"ROAD_{uuid.uuid4().hex[:6].upper()}"
    dept = dept_service.create_department(name=f"Road Wing {code}", code=code)

    # Add active incident
    db = get_session_factory()()
    inc = Incident(
        id=str(uuid.uuid4()),
        description="Active unresolved pothole",
        category="pothole",
        status="in_progress",
        priority="high",
        department_id=dept["id"],
        latitude=12.9716,
        longitude=77.5946,
        created_at=datetime.now(timezone.utc)
    )
    db.add(inc)
    db.commit()
    db.close()

    # Attempt to deactivate
    with pytest.raises(ValidationError, match="Cannot deactivate department"):
        dept_service.update_department(dept_id=dept["id"], is_active=False)

    # Now resolve incident
    db = get_session_factory()()
    inc_db = db.query(Incident).filter_by(id=inc.id).one()
    inc_db.status = "resolved"
    db.commit()
    db.close()

    # Now deactivation succeeds
    updated = dept_service.update_department(dept_id=dept["id"], is_active=False)
    assert updated["is_active"] is False


def test_officer_onboarding_and_memberships(app, dept_service):
    """Onboards an officer and validates department membership."""
    code = f"SEW_{uuid.uuid4().hex[:6].upper()}"
    dept = dept_service.create_department(name=f"Sewerage {code}", code=code)

    email = f"officer_{uuid.uuid4().hex[:6]}@civiclens.gov.in"
    officer = dept_service.onboard_officer(
        display_name="Inspector Vijay",
        email=email,
        password="SecurePassword123",
        role="municipal_officer",
        department_id=dept["id"],
        role_in_dept="officer"
    )

    assert officer["email"] == email
    assert officer["role"] == "municipal_officer"
    assert officer["department_id"] == dept["id"]

    # Verify in DB
    db = get_session_factory()()
    u = db.query(User).filter_by(id=officer["id"]).one()
    assert u.role == "municipal_officer"
    assert len(u.department_memberships) == 1
    assert u.department_memberships[0].department_id == dept["id"]
    db.close()


def test_officer_workload_aggregation(app, dept_service):
    """Calculates active tasks count accurately for officers."""
    code = f"LIGHT_{uuid.uuid4().hex[:6].upper()}"
    dept = dept_service.create_department(name=f"Lighting {code}", code=code)

    email = f"officer_{uuid.uuid4().hex[:6]}@civiclens.gov.in"
    officer = dept_service.onboard_officer(
        display_name="Linesman Prakash",
        email=email,
        password="SecurePassword123",
        role="municipal_officer",
        department_id=dept["id"]
    )

    # Assign 2 active incidents and 1 resolved incident
    db = get_session_factory()()
    inc1 = Incident(
        id=str(uuid.uuid4()),
        description="Broken lamp 1",
        category="broken_streetlight",
        status="assigned",
        assigned_officer_id=officer["id"],
        latitude=12.9716,
        longitude=77.5946
    )
    inc2 = Incident(
        id=str(uuid.uuid4()),
        description="Broken lamp 2",
        category="broken_streetlight",
        status="in_progress",
        assigned_officer_id=officer["id"],
        latitude=12.9716,
        longitude=77.5946
    )
    inc3 = Incident(
        id=str(uuid.uuid4()),
        description="Repaired lamp 3",
        category="broken_streetlight",
        status="resolved",
        assigned_officer_id=officer["id"],
        latitude=12.9716,
        longitude=77.5946
    )
    db.add_all([inc1, inc2, inc3])
    db.commit()
    db.close()

    officers = dept_service.list_officers(department_id=dept["id"])
    target = next((o for o in officers if o["id"] == officer["id"]), None)
    assert target is not None
    assert target["active_incidents_count"] == 2
    assert target["resolved_incidents_count"] == 1
