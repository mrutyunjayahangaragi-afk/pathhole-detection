"""
Inspection and Resolution Workflow Test Suite
=============================================
Verifies on-site physical inspection recording, priority escalation,
work progress milestones, hold reason guards, mandatory before/after photo pairing,
and evidence asset uploading.
"""

import uuid
import pytest
from datetime import datetime, timezone

from backend.db.engine import get_session_factory
from backend.db.models import Incident, User, InspectionRecord, WorkProgressUpdate, ResolutionRecord, EvidenceAsset
from backend.services.inspection_resolution_service import InspectionResolutionService
from backend.errors import ValidationError, NotFoundError


@pytest.fixture
def insp_service():
    return InspectionResolutionService()


@pytest.fixture
def sample_incident(app):
    db = get_session_factory()()
    inc = Incident(
        id=str(uuid.uuid4()),
        description="Deep pothole in outer lane",
        category="pothole",
        status="in_progress",
        priority="normal",
        latitude=12.9716,
        longitude=77.5946
    )
    db.add(inc)
    db.commit()
    inc_id = inc.id
    db.close()
    return inc_id


def create_officer():
    db = get_session_factory()()
    u = User(
        id=str(uuid.uuid4()),
        display_name="Inspector Ananya",
        email=f"ananya_{uuid.uuid4().hex[:6]}@civiclens.gov.in",
        role="municipal_officer",
        is_active=True
    )
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid


def create_evidence_asset(filename="photo.jpg"):
    db = get_session_factory()()
    ea = EvidenceAsset(
        id=str(uuid.uuid4()),
        content_sha256=uuid.uuid4().hex,
        storage_key=f"uploads/test_{uuid.uuid4().hex[:8]}.jpg",
        media_type="image/jpeg",
        file_size_bytes=1024,
        original_filename=filename
    )
    db.add(ea)
    db.commit()
    ea_id = ea.id
    db.close()
    return ea_id


def test_record_inspection_with_priority_escalation(insp_service, sample_incident):
    """Records an inspection and automatically escalates incident priority on critical hazard."""
    officer_id = create_officer()
    asset_id = create_evidence_asset("site_photo.jpg")

    res = insp_service.record_inspection(
        incident_id=sample_incident,
        officer_id=officer_id,
        findings="Massive 15cm deep pothole exposing road sub-base",
        confirmed_defect_type="pothole",
        condition_rating="critical",
        evidence_asset_id=asset_id,
        next_action="emergency_patch"
    )

    assert res["condition_rating"] == "critical"
    assert res["next_action"] == "emergency_patch"

    # Verify incident priority escalated to critical
    db = get_session_factory()()
    inc = db.query(Incident).filter_by(id=sample_incident).one()
    assert inc.priority == "critical"
    db.close()


def test_work_progress_and_hold_reason(insp_service, sample_incident):
    """Records work progress and enforces hold reason when placing on hold."""
    officer_id = create_officer()

    # Assign officer to the incident
    db = get_session_factory()()
    inc = db.query(Incident).filter_by(id=sample_incident).one()
    inc.assigned_officer_id = officer_id
    db.commit()
    db.close()

    # Progress milestone
    p1 = insp_service.record_work_progress(
        incident_id=sample_incident,
        officer_id=officer_id,
        stage="Excavation and edge trimming complete"
    )
    assert p1["stage"] == "Excavation and edge trimming complete"

    # Placing on hold without reason fails
    with pytest.raises(ValidationError, match="hold reason"):
        insp_service.record_work_progress(
            incident_id=sample_incident,
            officer_id=officer_id,
            stage="On Hold",
            hold_reason=""
        )

    # Placing on hold with reason succeeds and transitions incident status
    p2 = insp_service.record_work_progress(
        incident_id=sample_incident,
        officer_id=officer_id,
        stage="Work On Hold",
        hold_reason="Continuous torrential monsoon rain preventing asphalt application"
    )
    assert p2["hold_reason"] is not None

    db = get_session_factory()()
    inc = db.query(Incident).filter_by(id=sample_incident).one()
    assert inc.status == "on_hold"
    db.close()


def test_record_resolution_requires_after_evidence(insp_service, sample_incident):
    """Resolution strictly requires mandatory photographic evidence of completed repair."""
    officer_id = create_officer()
    before_asset = create_evidence_asset("before_pothole.jpg")
    after_asset = create_evidence_asset("after_repaired.jpg")

    # Assign officer to the incident
    db = get_session_factory()()
    inc = db.query(Incident).filter_by(id=sample_incident).one()
    inc.assigned_officer_id = officer_id
    db.commit()
    db.close()

    # Missing after evidence fails
    with pytest.raises(ValidationError, match="Mandatory 'after' photographic evidence"):
        insp_service.record_resolution(
            incident_id=sample_incident,
            resolved_by=officer_id,
            resolution_notes="Repaired with hot-mix asphalt and compacted.",
            after_evidence_id="",
            before_evidence_id=before_asset
        )

    # Missing detailed notes fails
    with pytest.raises(ValidationError, match="Detailed resolution notes"):
        insp_service.record_resolution(
            incident_id=sample_incident,
            resolved_by=officer_id,
            resolution_notes="Done",
            after_evidence_id=after_asset
        )

    # Valid resolution pairs before/after and transitions incident to resolved
    res = insp_service.record_resolution(
        incident_id=sample_incident,
        resolved_by=officer_id,
        resolution_notes="Excavated sub-base, filled with dense bituminous macadam and compacted with 8-ton vibratory roller.",
        after_evidence_id=after_asset,
        before_evidence_id=before_asset
    )

    assert res["after_evidence_id"] == after_asset
    assert res["before_evidence_id"] == before_asset

    db = get_session_factory()()
    inc = db.query(Incident).filter_by(id=sample_incident).one()
    assert inc.status == "resolved"
    db.close()


def test_upload_evidence_asset(insp_service, app):
    """Uploads binary file bytes, generates SHA-256 and persists EvidenceAsset."""
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + (b"\x00" * 100)
    uploaded = insp_service.upload_evidence_asset(
        raw_bytes=fake_jpeg,
        orig_name="field_repair.jpg",
        mime="image/jpeg"
    )

    assert "asset_id" in uploaded
    assert uploaded["media_type"] == "image/jpeg"
    assert uploaded["file_size"] == len(fake_jpeg)

    # Deduplication test: re-uploading returns existing asset
    dup = insp_service.upload_evidence_asset(
        raw_bytes=fake_jpeg,
        orig_name="field_repair.jpg",
        mime="image/jpeg"
    )
    assert dup["asset_id"] == uploaded["asset_id"]
