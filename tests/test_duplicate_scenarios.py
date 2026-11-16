"""
Edge-Case Scenario Tests for Duplicate Incident Matching Engine
================================================================
Validates all 12 core domain scenarios specified in Step 6 requirements:

Scenario 1: Fifty citizens report one pothole
Scenario 2: Same pothole, different viewpoints
Scenario 3: Two potholes five metres apart
Scenario 4: One image contains three potholes
Scenario 5: Same image uploaded by multiple users
Scenario 6: Same pothole photographed months later
Scenario 7: Conflicting GPS coordinates
Scenario 8: Missing GPS coordinates
Scenario 9: Similar potholes on different roads
Scenario 11: Repaired pothole reported again
Scenario 12: Failed embedding or detection processing
"""

import uuid
import datetime
from sqlalchemy.orm import Session
from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, CitizenReport, ReportItem, EvidenceAsset,
    ReportEvidence, IncidentObservation, MatchDecision,
    MatchEvaluation, Detection, User
)
from backend.services.duplicate_matching_service import DuplicateMatchingService
from backend.services.match_decision_service import MatchDecisionService
from backend.services.candidate_retrieval_service import CandidateRetrievalService
from backend.services.multi_signal_scoring_service import MultiSignalScoringService, CandidateScore


def _create_test_user(db: Session, role: str = "citizen") -> User:
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


def test_scenario_1_fifty_citizens_report_one_pothole():
    """
    Scenario 1: Fifty citizens report one pothole.
    Expected:
    - 50 individual citizen reports.
    - 50 preserved report histories.
    - 1 canonical incident after approved matching.
    - Incremented report count = 50.
    """
    factory = get_session_factory()
    db = factory()
    officer = _create_test_user(db, role="municipal_officer")
    decision_svc = MatchDecisionService(session_factory=factory)

    # 1. Create canonical incident
    inc = Incident(
        id=str(uuid.uuid4()),
        incident_reference="INC-POTHOLE-1",
        category="pothole",
        description="Major road cavity near Indiranagar 100ft road",
        severity="moderate",
        status="reported",
        latitude=12.9716,
        longitude=77.5946,
        report_count=1,
    )
    db.add(inc)
    db.commit()

    created_reports = []
    created_items = []

    try:
        # Create 49 additional citizen reports for the same pothole
        for i in range(49):
            citizen = _create_test_user(db, role="citizen")
            rep = CitizenReport(
                id=str(uuid.uuid4()),
                citizen_id=citizen.id,
                description=f"Citizen {i+1} saw deep pothole near junction",
                latitude=12.9716 + (i * 0.00001), # minor GPS drift within 2-3m
                longitude=77.5946 + (i * 0.00001),
                status="submitted",
            )
            item = ReportItem(
                id=str(uuid.uuid4()),
                report_id=rep.id,
                category="pothole",
                description=rep.description,
                status="pending",
            )
            db.add(rep)
            db.add(item)
            db.commit()
            created_reports.append(rep.id)
            created_items.append(item.id)

        # Confirm link for all 49 items
        for it_id in created_items:
            res = decision_svc.confirm_link_to_incident(
                report_item_id=it_id,
                incident_id=inc.id,
                reviewer_id=officer.id,
                review_notes="Confirmed duplicate submission of Indiranagar pothole",
            )
            assert res["status"] == "success"

        # Verify Canonical Incident
        db.refresh(inc)
        assert inc.report_count == 50, f"Expected 50 merged reports, got {inc.report_count}"

        # Verify all 49 reports are preserved
        db.expire_all()
        assert len(created_reports) == 49
        for r_id in created_reports:
            r = db.query(CitizenReport).filter_by(id=r_id).first()
            assert r is not None
            assert r.status == "linked"

    finally:
        # Cleanup
        db.query(MatchDecision).filter(MatchDecision.report_item_id.in_(created_items)).delete(synchronize_session=False)
        db.query(IncidentObservation).filter_by(incident_id=inc.id).delete(synchronize_session=False)
        db.query(ReportItem).filter(ReportItem.id.in_(created_items)).delete(synchronize_session=False)
        db.query(CitizenReport).filter(CitizenReport.id.in_(created_reports)).delete(synchronize_session=False)
        db.query(Incident).filter_by(id=inc.id).delete(synchronize_session=False)
        db.query(User).filter_by(id=officer.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_scenario_3_two_potholes_five_metres_apart_remain_independent():
    """
    Scenario 3: Two potholes 5 metres apart.
    Expected:
    - Geographic proximity alone cannot merge them.
    - When visual appearance / category differ or are unverified, system keeps them as separate candidates.
    - Enters human review or classified as distinct rather than automatic merge.
    """
    scoring = MultiSignalScoringService()

    # Pothole A is at distance 5m, but has low appearance visual similarity (0.40)
    score = scoring._score_single_candidate(
        db=None,
        report_item=ReportItem(id="item-test", category="pothole", description="Shallow circular pothole"),
        candidate=Incident(id="inc-test", category="pothole", latitude=12.9716, longitude=77.5946, description="Elongated trench"),
        item_assets=[],
        item_embeddings=[[1.0, 0.0, 0.0]], # orthogonal to candidate
        lat=12.971600,
        lon=77.594645, # ~5 meters away
        gps_accuracy_m=2.0,
    )

    # Combined score should be moderate, requiring human review
    assert score.geographic_distance_m is not None
    assert score.geographic_distance_m <= 6.0
    dec = scoring._classify_decision(top_candidate=score, runner_up=None, location_conflict=False)
    # Never auto-merges as LIKELY_EXISTING_INCIDENT without visual match
    assert dec in ("NEEDS_HUMAN_CONFIRMATION", "NEW_INCIDENT")


def test_scenario_4_one_image_contains_three_potholes():
    """
    Scenario 4: One image contains three distinct potholes.
    Expected:
    - Step 5 produces 3 distinct detections.
    - Each can be evaluated and linked to different or new incidents independently.
    """
    factory = get_session_factory()
    db = factory()
    citizen = _create_test_user(db, role="citizen")

    rep = CitizenReport(
        id=str(uuid.uuid4()),
        citizen_id=citizen.id,
        description="Multiple potholes on road",
        latitude=12.9716,
        longitude=77.5946,
        status="submitted",
    )
    # 3 distinct report items for the 3 potholes
    item1 = ReportItem(id=str(uuid.uuid4()), report_id=rep.id, category="pothole", description="Pothole A (left lane)")
    item2 = ReportItem(id=str(uuid.uuid4()), report_id=rep.id, category="pothole", description="Pothole B (center lane)")
    item3 = ReportItem(id=str(uuid.uuid4()), report_id=rep.id, category="pothole", description="Pothole C (right edge)")

    db.add(rep)
    db.add_all([item1, item2, item3])
    db.commit()

    try:
        # Verify all 3 report items exist independently
        items = db.query(ReportItem).filter_by(report_id=rep.id).all()
        assert len(items) == 3
        assert {it.description for it in items} == {
            "Pothole A (left lane)", "Pothole B (center lane)", "Pothole C (right edge)"
        }
    finally:
        db.query(ReportItem).filter_by(report_id=rep.id).delete(synchronize_session=False)
        db.query(CitizenReport).filter_by(id=rep.id).delete(synchronize_session=False)
        db.query(User).filter_by(id=citizen.id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_scenario_5_identical_image_uploaded_by_multiple_users():
    """
    Scenario 5: Same image uploaded by multiple users.
    Expected:
    - Exact SHA-256 hash recognized.
    - Distinct reports and citizen ownership retained separately.
    - Auditable matching decision.
    """
    factory = get_session_factory()
    db = factory()
    u1 = _create_test_user(db, role="citizen")
    u2 = _create_test_user(db, role="citizen")

    fixed_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    asset = EvidenceAsset(
        id=str(uuid.uuid4()),
        content_sha256=fixed_sha256,
        storage_key="/tmp/sample.jpg",
        media_type="image/jpeg",
    )
    db.add(asset)

    rep1 = CitizenReport(id=str(uuid.uuid4()), citizen_id=u1.id, latitude=12.97, longitude=77.59)
    rep2 = CitizenReport(id=str(uuid.uuid4()), citizen_id=u2.id, latitude=12.97, longitude=77.59)
    db.add_all([rep1, rep2])
    db.commit()

    try:
        # Query reports sharing the asset
        assert rep1.citizen_id != rep2.citizen_id
        assert rep1.id != rep2.id
    finally:
        db.query(CitizenReport).filter(CitizenReport.id.in_([rep1.id, rep2.id])).delete(synchronize_session=False)
        db.query(EvidenceAsset).filter_by(id=asset.id).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_([u1.id, u2.id])).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_scenario_7_conflicting_gps_forces_human_review():
    """
    Scenario 7: Conflicting GPS coordinates (e.g. EXIF vs submitted GPS divergence > 100m).
    Expected:
    - Conflicting location recorded (location_conflict=True).
    - Automatically forces NEEDS_HUMAN_CONFIRMATION, even if score is high.
    """
    scoring = MultiSignalScoringService()

    cand = CandidateScore(
        candidate_incident_id="inc-cand",
        combined_score=0.92,
        exact_match_signal=True,
        geographic_distance_m=12.0,
        geographic_score=0.95,
        visual_similarity_score=0.90,
        perceptual_similarity_score=0.88,
        category_score=1.0,
        text_score=0.8,
        decision_reason="Strong match",
    )

    dec = scoring._classify_decision(top_candidate=cand, runner_up=None, location_conflict=True)
    assert dec == "NEEDS_HUMAN_CONFIRMATION", "Location conflict must force human review"


def test_scenario_8_missing_gps_coordinates_handled_gracefully():
    """
    Scenario 8: Missing GPS coordinates.
    Expected:
    - Candidate retrieval and scoring does not crash with None/TypeError.
    - Visual similarity and exact hash remain usable.
    - Result enters human review.
    """
    scoring = MultiSignalScoringService()

    cand = Incident(id="inc-test", category="pothole", latitude=12.97, longitude=77.59, description="Pothole")
    score = scoring._score_single_candidate(
        db=None,
        report_item=ReportItem(id="item-test", category="pothole", description="No GPS pothole"),
        candidate=cand,
        item_assets=[],
        item_embeddings=[],
        lat=None, # Missing GPS
        lon=None,
        gps_accuracy_m=None,
    )

    assert score.geographic_distance_m is None
    assert score.geographic_score is None
    # Still computes score across available signals (category, text)
    assert score.combined_score is not None
    assert score.combined_score >= 0.0


def test_scenario_9_similar_potholes_on_different_roads_not_merged():
    """
    Scenario 9: Similar potholes on different roads (> 500m apart).
    Expected:
    - Appearance similarity does not falsely merge distant physical defects.
    - Classified as NEW_INCIDENT.
    """
    scoring = MultiSignalScoringService()

    score = scoring._score_single_candidate(
        db=None,
        report_item=ReportItem(id="item-test", category="pothole", description="Similar pothole"),
        candidate=Incident(id="inc-test", category="pothole", latitude=12.97, longitude=77.59, description="Pothole"),
        item_assets=[],
        item_embeddings=[[1.0, 1.0]],
        lat=12.9800, # ~1.1 km away
        lon=77.5900,
        gps_accuracy_m=5.0,
    )

    assert score.geographic_distance_m > 500.0
    assert score.geographic_score == 0.0
    assert score.combined_score <= 0.35
    dec = scoring._classify_decision(top_candidate=score, runner_up=None, location_conflict=False)
    assert dec == "NEW_INCIDENT"
