"""
Domain Rules Test Suite
=======================

Verifies the 5 core domain invariants specified in CivicLens Step 2:
1. Several citizen reports can refer to one incident.
2. One report can contain multiple evidence assets.
3. One media file can contain multiple defect detections.
4. An uncertain match does not automatically merge incidents.
5. An individual report remains independently identifiable.
"""

import pytest
import time
import uuid

from backend.domain.models import (
    Incident,
    CitizenReport,
    EvidenceAsset,
    Detection,
    MatchDecision,
    MatchVerdict,
    SeverityLevel,
    IncidentStatus,
    SourceType,
)
from backend.domain.rules import CivicLensDomainRules


def test_several_citizen_reports_can_refer_to_one_incident():
    """
    Domain Rule 1: One physical infrastructure issue = One canonical incident,
    with multiple citizens reporting it without creating multiple duplicate incidents.
    """
    # Create canonical incident
    canonical_incident = Incident(
        latitude=8.5241,
        longitude=76.9366,
        severity=SeverityLevel.MINOR,
        est_depth_cm=2.0,
        status=IncidentStatus.REPORTED,
        report_count=1,
    )

    # First report from Citizen A
    report_a = CitizenReport(
        citizen_id="citizen-001",
        latitude=8.52412,
        longitude=76.93661,
        description="Pothole near market entrance",
        language_code="en",
    )
    canonical_incident.record_additional_report(report_a, new_depth_cm=2.5, new_severity=SeverityLevel.MODERATE)

    # Second report from Citizen B (in Kannada)
    report_b = CitizenReport(
        citizen_id="citizen-002",
        latitude=8.52408,
        longitude=76.93659,
        description="ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಇದೆ",
        language_code="kn",
    )
    canonical_incident.record_additional_report(report_b, new_depth_cm=5.2, new_severity=SeverityLevel.SEVERE)

    # Third report from automated vehicle telematics
    report_c = CitizenReport(
        vehicle_id="bus-042",
        source_type=SourceType.VEHICLE_TELEMATICS,
        latitude=8.52410,
        longitude=76.93660,
    )
    canonical_incident.record_additional_report(report_c, new_depth_cm=4.0)

    # Assertions
    assert canonical_incident.report_count == 4
    assert len(canonical_incident.reports) == 3
    assert canonical_incident.severity == SeverityLevel.SEVERE  # Upgraded to worst severity
    assert canonical_incident.est_depth_cm == 5.2              # Maximized depth
    assert all(r.incident_id == canonical_incident.id for r in canonical_incident.reports)


def test_one_report_can_contain_multiple_evidence_assets():
    """
    Domain Rule 2: One citizen report can contain multiple distinct evidence assets
    (e.g., wide angle context photo + close-up depth photo).
    """
    report = CitizenReport(
        citizen_id="citizen-105",
        latitude=8.4855,
        longitude=76.9492,
    )

    asset_1 = EvidenceAsset(
        report_id=report.id,
        file_path="uploads/photo1_wide.jpg",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        file_size_bytes=102400,
    )
    asset_2 = EvidenceAsset(
        report_id=report.id,
        file_path="uploads/photo2_closeup.jpg",
        sha256_hash="cca9203a30282b04753063f2349e5d4cb077d28741369b50b522cbcfd70390a8",
        file_size_bytes=81920,
    )

    report.evidence_assets.extend([asset_1, asset_2])

    assert len(report.evidence_assets) == 2
    assert CivicLensDomainRules.assert_multiple_evidence_per_report(report, report.evidence_assets)
    assert report.evidence_assets[0].sha256_hash != report.evidence_assets[1].sha256_hash


def test_one_media_file_can_contain_multiple_detections():
    """
    Domain Rule 3: A single image or media asset can contain multiple distinct
    defect detections (e.g., two potholes in the same roadway photo).
    """
    asset = EvidenceAsset(
        file_path="uploads/road_section.jpg",
        sha256_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    )

    # Two distinct bounding boxes found by YOLO in the same frame
    detection_1 = Detection(
        evidence_asset_id=asset.id,
        defect_type="pothole",
        bbox_x=120,
        bbox_y=340,
        bbox_w=85,
        bbox_h=60,
        confidence=0.88,
        severity=SeverityLevel.MODERATE,
    )
    detection_2 = Detection(
        evidence_asset_id=asset.id,
        defect_type="pothole",
        bbox_x=450,
        bbox_y=280,
        bbox_w=120,
        bbox_h=95,
        confidence=0.92,
        severity=SeverityLevel.SEVERE,
    )

    detections = [detection_1, detection_2]

    assert len(detections) == 2
    assert CivicLensDomainRules.assert_multiple_detections_per_media(asset, detections)
    assert detection_1.id != detection_2.id
    assert detection_1.severity != detection_2.severity


def test_uncertain_match_does_not_auto_merge():
    """
    Domain Rule 4: An uncertain match (PROBABLE_MATCH) must NOT automatically
    merge incidents. It must be held for human/municipal verification or citizen confirmation.
    """
    # Uncertain decision (e.g. distance is near boundary or low visual confidence)
    uncertain_decision = MatchDecision(
        report_id=str(uuid.uuid4()),
        candidate_incident_id=str(uuid.uuid4()),
        verdict=MatchVerdict.PROBABLE_MATCH,
        confidence_score=0.65,
        spatial_distance_m=13.8,
        reason="Borderline distance (13.8m)",
    )

    # Invariant: can_auto_merge must be FALSE
    assert CivicLensDomainRules.can_auto_merge(uncertain_decision) is False

    # Confirmed exact duplicate
    exact_decision = MatchDecision(
        report_id=str(uuid.uuid4()),
        candidate_incident_id=str(uuid.uuid4()),
        verdict=MatchVerdict.EXACT_DUPLICATE,
        confidence_score=0.95,
        spatial_distance_m=2.1,
        reason="High spatial and visual match",
    )

    # Invariant: can_auto_merge must be TRUE
    assert CivicLensDomainRules.can_auto_merge(exact_decision) is True


def test_individual_report_remains_independently_identifiable():
    """
    Domain Rule 5: When multiple reports are associated with one incident,
    each report retains its own unique identity, timestamps, citizen ID, and source.
    """
    incident = Incident(latitude=8.5241, longitude=76.9366)

    report_1 = CitizenReport(
        citizen_id="citizen-alpha",
        latitude=8.52411,
        longitude=76.93662,
        description="First observation in morning",
        created_at=1000.0,
    )
    report_2 = CitizenReport(
        citizen_id="citizen-beta",
        latitude=8.52409,
        longitude=76.93658,
        description="Second observation at night",
        created_at=2000.0,
    )

    incident.record_additional_report(report_1)
    incident.record_additional_report(report_2)

    assert CivicLensDomainRules.assert_independent_report_identity(incident, [report_1, report_2])
    assert report_1.id != report_2.id
    assert report_1.citizen_id != report_2.citizen_id
    assert report_1.created_at != report_2.created_at
    assert report_1.incident_id == incident.id
    assert report_2.incident_id == incident.id
