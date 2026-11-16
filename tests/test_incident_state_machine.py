"""
Incident Lifecycle State Machine Test Suite
===========================================
Verifies that canonical incident state progressions follow the state graph,
enforce role transition permissions, record audit history, and synchronize
linked citizen complaints on resolution.
"""

import uuid
import pytest
from datetime import datetime, timezone

from backend.db.engine import get_session_factory
from backend.db.models import Incident, CitizenReport, ReportItem, IncidentStatusHistory, AuditLog, CitizenVisibleUpdate, User
from backend.services.incident_state_machine_service import IncidentStateMachineService, IncidentStatus
from backend.errors import ValidationError, NotFoundError


def create_test_user(db, role="municipal_admin"):
    u = User(
        id=str(uuid.uuid4()),
        display_name=f"Test {role}",
        email=f"user_{uuid.uuid4().hex[:6]}@civiclens.gov.in",
        role=role,
        is_active=True
    )
    db.add(u)
    db.commit()
    return u.id


@pytest.fixture
def state_machine():
    return IncidentStateMachineService()


@pytest.fixture
def sample_incident(app):
    db = get_session_factory()()
    inc = Incident(
        id=str(uuid.uuid4()),
        description="Severe pothole on 80 Feet Road",
        category="pothole",
        status=IncidentStatus.NEW,
        priority="normal",
        latitude=12.9716,
        longitude=77.5946,
        created_at=datetime.now(timezone.utc)
    )
    db.add(inc)
    db.commit()
    inc_id = inc.id
    db.close()
    return inc_id


def test_valid_transition_lifecycle(state_machine, sample_incident):
    """Executes a full standard lifecycle from NEW to CLOSED."""
    db = get_session_factory()()
    actor_id = create_test_user(db, "municipal_admin")
    db.close()
    role = "municipal_admin"

    # 1. new -> awaiting_verification
    res = state_machine.transition_incident(
        incident_id=sample_incident,
        new_status=IncidentStatus.AWAITING_VERIFICATION,
        actor_id=actor_id,
        actor_role=role,
        reason="Sensor data uploaded, pending human check"
    )
    assert res["new_status"] == IncidentStatus.AWAITING_VERIFICATION

    # 2. awaiting_verification -> verified
    res = state_machine.transition_incident(
        incident_id=sample_incident,
        new_status=IncidentStatus.VERIFIED,
        actor_id=actor_id,
        actor_role=role,
        reason="Field photos verified"
    )
    assert res["new_status"] == IncidentStatus.VERIFIED

    # 3. verified -> assigned
    res = state_machine.transition_incident(
        incident_id=sample_incident,
        new_status=IncidentStatus.ASSIGNED,
        actor_id=actor_id,
        actor_role=role,
        reason="Assigned to Road Maintenance crew"
    )
    assert res["new_status"] == IncidentStatus.ASSIGNED

    # 4. assigned -> in_progress
    res = state_machine.transition_incident(
        incident_id=sample_incident,
        new_status=IncidentStatus.IN_PROGRESS,
        actor_id=actor_id,
        actor_role=role,
        reason="Crew on site with asphalt roller"
    )
    assert res["new_status"] == IncidentStatus.IN_PROGRESS

    # 5. in_progress -> on_hold
    res = state_machine.transition_incident(
        incident_id=sample_incident,
        new_status=IncidentStatus.ON_HOLD,
        actor_id=actor_id,
        actor_role=role,
        reason="Heavy rain interrupted asphalt laying"
    )
    assert res["new_status"] == IncidentStatus.ON_HOLD

    # 6. on_hold -> in_progress
    res = state_machine.transition_incident(
        incident_id=sample_incident,
        new_status=IncidentStatus.IN_PROGRESS,
        actor_id=actor_id,
        actor_role=role,
        reason="Rain cleared, resumed compaction"
    )
    assert res["new_status"] == IncidentStatus.IN_PROGRESS

    # 7. in_progress -> resolved
    res = state_machine.transition_incident(
        incident_id=sample_incident,
        new_status=IncidentStatus.RESOLVED,
        actor_id=actor_id,
        actor_role=role,
        reason="Pothole filled and sealed completely"
    )
    assert res["new_status"] == IncidentStatus.RESOLVED

    # 8. resolved -> closed
    res = state_machine.transition_incident(
        incident_id=sample_incident,
        new_status=IncidentStatus.CLOSED,
        actor_id=actor_id,
        actor_role=role,
        reason="Quality assurance audit approved"
    )
    assert res["new_status"] == IncidentStatus.CLOSED

    # Verify history and audit trail
    db = get_session_factory()()
    history = db.query(IncidentStatusHistory).filter_by(incident_id=sample_incident).all()
    assert len(history) == 8

    audits = db.query(AuditLog).filter_by(entity_id=sample_incident, action="incident_status_transition").all()
    assert len(audits) == 8
    db.close()


def test_invalid_transitions_blocked(state_machine, sample_incident):
    """Direct illegal jumps in the state machine graph raise ValidationError."""
    actor_id = str(uuid.uuid4())

    # new -> closed is invalid
    with pytest.raises(ValidationError, match="Cannot transition incident"):
        state_machine.transition_incident(
            incident_id=sample_incident,
            new_status=IncidentStatus.CLOSED,
            actor_id=actor_id,
            actor_role="municipal_admin",
            reason="Illegal skip"
        )

    # new -> in_progress is invalid (must verify first)
    with pytest.raises(ValidationError, match="Cannot transition incident"):
        state_machine.transition_incident(
            incident_id=sample_incident,
            new_status=IncidentStatus.IN_PROGRESS,
            actor_id=actor_id,
            actor_role="municipal_admin",
            reason="Illegal jump"
        )


def test_transition_requires_mandatory_reason(state_machine, sample_incident):
    """Transitions without a clear reason are rejected."""
    actor_id = str(uuid.uuid4())

    with pytest.raises(ValidationError, match="A clear reason"):
        state_machine.transition_incident(
            incident_id=sample_incident,
            new_status=IncidentStatus.AWAITING_VERIFICATION,
            actor_id=actor_id,
            actor_role="municipal_admin",
            reason=""
        )


def test_citizen_report_synchronization_on_resolved(state_machine, sample_incident):
    """Linked citizen reports are automatically marked resolved when incident resolves."""
    db = get_session_factory()()
    citizen_user_id = create_test_user(db, "citizen")

    rep1 = CitizenReport(
        id=str(uuid.uuid4()),
        citizen_id=citizen_user_id,
        title="Citizen complaint 1",
        description="Pothole description",
        status="submitted",
        latitude=12.9716,
        longitude=77.5946,
        created_at=datetime.now(timezone.utc)
    )
    rep2 = CitizenReport(
        id=str(uuid.uuid4()),
        citizen_id=citizen_user_id,
        title="Citizen complaint 2",
        description="Second complaint at same spot",
        status="linked",
        latitude=12.9716,
        longitude=77.5946,
        created_at=datetime.now(timezone.utc)
    )
    db.add_all([rep1, rep2])
    db.flush()

    item1 = ReportItem(
        id=str(uuid.uuid4()),
        report_id=rep1.id,
        incident_id=sample_incident,
        category="pothole",
        description="Item 1"
    )
    item2 = ReportItem(
        id=str(uuid.uuid4()),
        report_id=rep2.id,
        incident_id=sample_incident,
        category="pothole",
        description="Item 2"
    )
    db.add_all([item1, item2])
    actor_id = create_test_user(db, "municipal_admin")
    db.commit()
    db.close()

    # Fast forward to in_progress
    state_machine.transition_incident(sample_incident, IncidentStatus.VERIFIED, actor_id, "municipal_admin", "Verified")
    state_machine.transition_incident(sample_incident, IncidentStatus.IN_PROGRESS, actor_id, "municipal_admin", "In repair")

    # Transition to RESOLVED
    res = state_machine.transition_incident(
        sample_incident,
        IncidentStatus.RESOLVED,
        actor_id,
        "municipal_admin",
        "Pothole repaired successfully with bitumen"
    )

    assert res["reports_synchronized"] == 2

    # Check database status
    db = get_session_factory()()
    r1 = db.query(CitizenReport).filter_by(id=rep1.id).one()
    r2 = db.query(CitizenReport).filter_by(id=rep2.id).one()
    assert r1.status == "resolved"
    assert r2.status == "resolved"

    # Check citizen visible update created
    updates = db.query(CitizenVisibleUpdate).filter_by(incident_id=sample_incident).all()
    assert len(updates) > 0
    assert "resolved" in updates[-1].public_message.lower()
    db.close()


def test_officer_cannot_unilaterally_close_or_reject(state_machine, sample_incident):
    """Field officers cannot unilaterally close or reject canonical incidents."""
    db = get_session_factory()()
    officer_id = create_test_user(db, "municipal_officer")

    # Assign officer to the incident first
    inc = db.query(Incident).filter_by(id=sample_incident).one()
    inc.assigned_officer_id = officer_id
    db.commit()
    db.close()

    with pytest.raises(ValidationError, match="cannot close or reject"):
        state_machine.transition_incident(
            incident_id=sample_incident,
            new_status=IncidentStatus.REJECTED,
            actor_id=officer_id,
            actor_role="municipal_officer",
            reason="Officer decided to reject"
        )
