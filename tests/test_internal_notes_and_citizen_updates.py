"""
Internal Notes and Citizen Updates Test Suite
=============================================
Verifies role-based visibility isolation for municipal internal notes
and public publishing of citizen-visible updates.
"""

import uuid
import pytest
from datetime import datetime, timezone

from backend.db.engine import get_session_factory
from backend.db.models import Incident, User, MunicipalInternalNote, CitizenVisibleUpdate
from backend.services.municipal_communication_service import MunicipalCommunicationService
from backend.errors import ValidationError, NotFoundError


@pytest.fixture
def comm_service():
    return MunicipalCommunicationService()


@pytest.fixture
def sample_incident(app):
    db = get_session_factory()()
    inc = Incident(
        id=str(uuid.uuid4()),
        description="Drainage block on 100 Feet Road",
        category="drainage",
        status="in_progress",
        latitude=12.9716,
        longitude=77.5946
    )
    db.add(inc)
    db.commit()
    inc_id = inc.id
    db.close()
    return inc_id


def create_user(role="municipal_officer"):
    db = get_session_factory()()
    u = User(
        id=str(uuid.uuid4()),
        display_name=f"User {uuid.uuid4().hex[:4]}",
        email=f"u_{uuid.uuid4().hex[:6]}@civiclens.gov.in",
        role=role,
        is_active=True
    )
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid


def test_internal_notes_audience_isolation(comm_service, sample_incident):
    """dept_admin_only notes are invisible to municipal_officer role."""
    admin_id = create_user("dept_admin")
    officer_id = create_user("municipal_officer")

    # Admin note
    comm_service.add_internal_note(
        incident_id=sample_incident,
        author_id=admin_id,
        content="Confidential contractor performance review pending for this work order",
        audience="dept_admin_only"
    )

    # General officer note
    comm_service.add_internal_note(
        incident_id=sample_incident,
        author_id=officer_id,
        content="Field inspection completed; safety barricades positioned",
        audience="internal_officers"
    )

    # Officer viewer sees only 1 note
    officer_notes = comm_service.list_internal_notes(sample_incident, viewer_role="municipal_officer")
    assert len(officer_notes) == 1
    assert "safety barricades" in officer_notes[0]["content"]

    # Dept Admin viewer sees both notes
    admin_notes = comm_service.list_internal_notes(sample_incident, viewer_role="dept_admin")
    assert len(admin_notes) == 2


def test_internal_note_validation(comm_service, sample_incident):
    """Rejects empty content and invalid audiences."""
    user_id = create_user()

    with pytest.raises(ValidationError, match="at least 3 characters"):
        comm_service.add_internal_note(sample_incident, user_id, "hi")

    with pytest.raises(ValidationError, match="Invalid note audience"):
        comm_service.add_internal_note(sample_incident, user_id, "Valid content", audience="public_all")


def test_citizen_updates_publishing(comm_service, sample_incident):
    """Citizen updates can be published and retrieved publicly."""
    user_id = create_user("municipal_officer")

    update = comm_service.publish_citizen_update(
        incident_id=sample_incident,
        published_by=user_id,
        public_message="Road maintenance crews have arrived on site and commenced pavement edge cutting.",
        status_label="Work In Progress"
    )

    assert update["status_label"] == "Work In Progress"

    updates = comm_service.list_citizen_updates(sample_incident)
    assert len(updates) == 1
    assert "pavement edge cutting" in updates[0]["public_message"]
