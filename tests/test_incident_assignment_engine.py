"""
Incident Assignment Engine Test Suite
=====================================
Verifies departmental routing, officer assignment, mandatory reassignment audit reasons,
department boundary validation, and assignment chronological history.
"""

import uuid
import pytest
from datetime import datetime, timezone

from backend.db.engine import get_session_factory
from backend.db.models import Incident, Department, DepartmentMembership, User, IncidentAssignment
from backend.services.incident_assignment_service import IncidentAssignmentService
from backend.services.department_management_service import DepartmentManagementService
from backend.errors import ValidationError, NotFoundError


@pytest.fixture
def assignment_service():
    return IncidentAssignmentService()


@pytest.fixture
def dept_service():
    return DepartmentManagementService()


@pytest.fixture
def sample_incident(app):
    db = get_session_factory()()
    inc = Incident(
        id=str(uuid.uuid4()),
        description="Pothole near junction",
        category="pothole",
        status="verified",
        priority="normal",
        latitude=12.9716,
        longitude=77.5946
    )
    db.add(inc)
    db.commit()
    inc_id = inc.id
    db.close()
    return inc_id


def create_user(role="municipal_officer", dept_id=None):
    db = get_session_factory()()
    u = User(
        id=str(uuid.uuid4()),
        display_name=f"Officer {uuid.uuid4().hex[:4]}",
        email=f"off_{uuid.uuid4().hex[:6]}@civiclens.gov.in",
        role=role,
        is_active=True
    )
    db.add(u)
    if dept_id:
        m = DepartmentMembership(
            id=str(uuid.uuid4()),
            user_id=u.id,
            department_id=dept_id,
            role_in_dept="officer",
            is_active=True
        )
        db.add(m)
    db.commit()
    user_id = u.id
    db.close()
    return user_id


def test_assign_incident_to_department(assignment_service, dept_service, sample_incident):
    """Assigns department and upgrades priority."""
    code = f"ROADS_{uuid.uuid4().hex[:6].upper()}"
    dept = dept_service.create_department(name=f"Roads {code}", code=code)
    admin_id = create_user("municipal_admin")

    res = assignment_service.assign_department(
        incident_id=sample_incident,
        department_id=dept["id"],
        assigned_by=admin_id,
        actor_role="municipal_admin",
        reason="Assigned to asphalt repair wing",
        priority="high"
    )

    assert res["department_id"] == dept["id"]
    assert res["status"] == "assigned"
    assert res["priority"] == "high"

    # Verify assignment record in DB
    db = get_session_factory()()
    assign = db.query(IncidentAssignment).filter_by(incident_id=sample_incident).first()
    assert assign is not None
    assert assign.department_id == dept["id"]
    db.close()


def test_reassignment_requires_mandatory_reason(assignment_service, dept_service, sample_incident):
    """Reassigning an incident from one officer to another requires a clear audit reason."""
    code = f"DRAIN_{uuid.uuid4().hex[:6].upper()}"
    dept = dept_service.create_department(name=f"Drainage {code}", code=code)
    admin_id = create_user("dept_admin", dept["id"])

    off1 = create_user("municipal_officer", dept["id"])
    off2 = create_user("municipal_officer", dept["id"])

    # Initial assignment to dept & off1
    assignment_service.assign_department(sample_incident, dept["id"], admin_id, "dept_admin")
    assignment_service.assign_officer(sample_incident, off1, admin_id, "dept_admin", "Initial shift")

    # Reassignment to off2 without reason should fail
    with pytest.raises(ValidationError, match="clear reason"):
        assignment_service.assign_officer(sample_incident, off2, admin_id, "dept_admin", reason="")

    # Reassignment with clear reason succeeds
    res = assignment_service.assign_officer(
        sample_incident,
        off2,
        admin_id,
        "dept_admin",
        reason="Officer 1 on emergency medical leave; reallocating task"
    )
    assert res["assigned_officer_id"] == off2


def test_officer_department_membership_check(assignment_service, dept_service, sample_incident):
    """Dept admin cannot assign incident to an officer from a different department."""
    dept1 = dept_service.create_department(name=f"Dept 1 {uuid.uuid4().hex[:4]}", code=f"D1_{uuid.uuid4().hex[:4].upper()}")
    dept2 = dept_service.create_department(name=f"Dept 2 {uuid.uuid4().hex[:4]}", code=f"D2_{uuid.uuid4().hex[:4].upper()}")

    da_id = create_user("dept_admin", dept1["id"])
    external_officer = create_user("municipal_officer", dept2["id"])

    # Assign incident to Dept 1
    assignment_service.assign_department(sample_incident, dept1["id"], da_id, "dept_admin")

    # Dept Admin tries to assign external officer to incident in Dept 1
    with pytest.raises(ValidationError, match="not an active member of the assigned department"):
        assignment_service.assign_officer(sample_incident, external_officer, da_id, "dept_admin", "Cross-dept test")


def test_assignment_history(assignment_service, dept_service, sample_incident):
    """Retrieves full chronological audit trail of incident assignments."""
    dept = dept_service.create_department(name=f"Dept {uuid.uuid4().hex[:4]}", code=f"DH_{uuid.uuid4().hex[:4].upper()}")
    admin_id = create_user("municipal_admin")
    off_id = create_user("municipal_officer", dept["id"])

    assignment_service.assign_department(sample_incident, dept["id"], admin_id, "municipal_admin", "First routing")
    assignment_service.assign_officer(sample_incident, off_id, admin_id, "municipal_admin", "Assigned field inspector")

    history = assignment_service.get_assignment_history(sample_incident)
    assert len(history) == 2
    assert history[0]["department_id"] == dept["id"]
    assert history[1]["assigned_officer_id"] == off_id
