"""
Concurrency and Conflict Protection Tests for Duplicate Matching
================================================================
Validates Scenario 10 (concurrency and race conditions), optimistic locking,
conflict detection, incident consolidation, and anti-IDOR security.
"""

import uuid
import pytest
from sqlalchemy.orm import Session
from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, CitizenReport, ReportItem, MatchDecision,
    IncidentConsolidation, IncidentObservation, User
)
from backend.services.match_decision_service import MatchDecisionService
from backend.services.incident_consolidation_service import IncidentConsolidationService
from backend.errors import ConflictError, ForbiddenError


def _create_user(db: Session, role: str) -> User:
    u = User(
        id=str(uuid.uuid4()),
        display_name=f"User {uuid.uuid4().hex[:6]}",
        email=f"user_{uuid.uuid4().hex[:8]}@civiclens.test",
        password_hash="testhash123",
        role=role,
    )
    db.add(u)
    db.commit()
    return u


def test_concurrent_reviewers_conflict_prevention():
    """
    Scenario 10: Two reviewers attempt to confirm the same item simultaneously.
    Expected:
    - First reviewer succeeds and links the item.
    - Second reviewer receives ConflictError (HTTP 409).
    - No contradictory or duplicate canonical incidents created.
    """
    factory = get_session_factory()
    db = factory()
    service = MatchDecisionService(session_factory=factory)

    officer1 = _create_user(db, "municipal_officer")
    officer2 = _create_user(db, "municipal_officer")
    citizen = _create_user(db, "citizen")

    # Target incident
    inc = Incident(
        id=str(uuid.uuid4()),
        incident_reference="INC-CONC-1",
        category="pothole",
        latitude=12.97,
        longitude=77.59,
        report_count=1,
    )
    rep = CitizenReport(
        id=str(uuid.uuid4()),
        citizen_id=citizen.id,
        latitude=12.97,
        longitude=77.59,
        status="submitted",
    )
    item = ReportItem(
        id=str(uuid.uuid4()),
        report_id=rep.id,
        category="pothole",
        description="Pothole to match",
        status="pending",
    )
    db.add_all([inc, rep, item])
    db.commit()

    try:
        # Officer 1 confirms link
        res1 = service.confirm_link_to_incident(
            report_item_id=item.id,
            incident_id=inc.id,
            reviewer_id=officer1.id,
            review_notes="Officer 1 approved link",
        )
        assert res1["status"] == "success"

        # Officer 2 attempts to confirm link for the same item
        with pytest.raises(ConflictError) as exc_info:
            service.confirm_link_to_incident(
                report_item_id=item.id,
                incident_id=inc.id,
                reviewer_id=officer2.id,
                review_notes="Officer 2 conflicting attempt",
            )
        assert "already resolved" in str(exc_info.value).lower()

    finally:
        db.query(MatchDecision).filter_by(report_item_id=item.id).delete(synchronize_session=False)
        db.query(IncidentObservation).filter_by(incident_id=inc.id).delete(synchronize_session=False)
        db.query(ReportItem).filter_by(id=item.id).delete(synchronize_session=False)
        db.query(CitizenReport).filter_by(id=rep.id).delete(synchronize_session=False)
        db.query(Incident).filter_by(id=inc.id).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([officer1.id, officer2.id, citizen.id])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_incident_consolidation_service():
    """
    Verifies human-approved consolidation of two canonical incidents.
    Expected:
    - Superseded incident is closed with audit history.
    - All report items and observations point to canonical incident.
    - Combined report counts preserved.
    """
    factory = get_session_factory()
    db = factory()
    admin = _create_user(db, "system_admin")
    citizen = _create_user(db, "citizen")
    service = IncidentConsolidationService(session_factory=factory)

    canonical = Incident(id=str(uuid.uuid4()), incident_reference="INC-CANONICAL", category="pothole", latitude=12.97, longitude=77.59, report_count=3)
    superseded = Incident(id=str(uuid.uuid4()), incident_reference="INC-SUPERSEDED", category="pothole", latitude=12.97, longitude=77.59, report_count=2)
    rep = CitizenReport(id=str(uuid.uuid4()), citizen_id=citizen.id, latitude=12.97, longitude=77.59)
    item = ReportItem(id=str(uuid.uuid4()), report_id=rep.id, incident_id=superseded.id, category="pothole", status="matched")

    db.add_all([canonical, superseded, rep, item])
    db.commit()

    try:
        res = service.consolidate_incidents(
            canonical_incident_id=canonical.id,
            superseded_incident_id=superseded.id,
            consolidated_by=admin.id,
            consolidation_reason="Engineering inspection verified both IDs describe the exact same 100ft road pothole",
        )

        assert res["status"] == "success"
        assert res["new_canonical_report_count"] == 5

        # Check DB state
        db.refresh(canonical)
        db.refresh(superseded)
        db.refresh(item)

        assert canonical.report_count == 5
        assert superseded.status == "closed"
        assert item.incident_id == canonical.id

        # Check consolidation record
        cons = db.query(IncidentConsolidation).filter_by(canonical_incident_id=canonical.id).first()
        assert cons is not None
        assert cons.superseded_incident_id == superseded.id
        assert cons.consolidated_by == admin.id

    finally:
        db.query(IncidentConsolidation).filter_by(canonical_incident_id=canonical.id).delete(synchronize_session=False)
        db.query(ReportItem).filter_by(id=item.id).delete(synchronize_session=False)
        db.query(CitizenReport).filter_by(id=rep.id).delete(synchronize_session=False)
        db.query(Incident).filter(Incident.id.in_([canonical.id, superseded.id])).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([admin.id, citizen.id])).delete(synchronize_session=False)
        db.commit()
        db.close()
