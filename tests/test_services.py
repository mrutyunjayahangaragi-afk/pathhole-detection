"""
Services Test Suite
===================

Tests individual service layer modules: LocationService, EvidenceService,
DuplicateMatchingService, and DetectionService.
"""

import tempfile
import pytest
from pathlib import Path

from backend.services.location_service import LocationService, haversine_distance_m
from backend.services.evidence_service import EvidenceService
from backend.services.detection_service import DetectionService
from backend.services.duplicate_matching_service import DuplicateMatchingService
from backend.domain.models import SeverityLevel, MatchVerdict
from backend.database import get_db, init_db
from backend.errors import ValidationError


def test_haversine_distance():
    """Verifies Haversine formula against known coordinates."""
    # Distance between two points in Thiruvananthapuram roughly 111m apart (0.001 deg lat)
    d = haversine_distance_m(8.5241, 76.9366, 8.5251, 76.9366)
    assert 110.0 < d < 112.5

    # Same coordinates should be 0 distance
    assert haversine_distance_m(8.5241, 76.9366, 8.5241, 76.9366) == 0.0


def test_location_service_reverse_geocode_fallback():
    """Verifies LocationService fallback returns formatted coordinate string when offline."""
    loc_service = LocationService()
    addr = loc_service.reverse_geocode(8.5241, 76.9366)
    # Even if offline, should return non-empty fallback string
    assert len(addr) > 0


def test_evidence_service_sha256_and_security(tmp_path):
    """Verifies EvidenceService computes SHA-256 and sanitizes filenames safely."""
    evidence_svc = EvidenceService(upload_dir=str(tmp_path))

    data = b"Simulated image data content"
    expected_sha256 = "0129c0973a9e331ae7de0aabefb29cde17c4a355f295acc3f00c3c8cd16ec42e"
    assert evidence_svc.compute_sha256(data) == expected_sha256

    # Test path traversal prevention in original filename
    malicious_filename = "../../../etc/passwd.jpg"
    safe_name = evidence_svc.sanitize_filename(malicious_filename)
    assert ".." not in safe_name
    assert "/" not in safe_name
    assert safe_name.endswith(".jpg")

    # Test unsupported extension rejection
    with pytest.raises(ValidationError, match="Unsupported file format"):
        evidence_svc.create_asset_from_bytes(data, "malicious_script.exe", "report-123")


def test_detection_service_validation():
    """Verifies DetectionService validates bounding boxes and defect severity."""
    det_svc = DetectionService()

    # Valid detection
    valid_payload = {
        "bbox": [10, 20, 100, 80],
        "confidence": 0.85,
        "severity": "moderate",
        "est_depth_cm": 3.5,
    }
    det = det_svc.create_detection_from_dict(valid_payload, evidence_asset_id="asset-001")
    assert det.bbox_x == 10
    assert det.severity == SeverityLevel.MODERATE
    assert det.confidence == 0.85

    # Invalid bbox (only 3 elements)
    with pytest.raises(ValidationError, match="Bounding box must contain exactly 4 integers"):
        det_svc.create_detection_from_dict({"bbox": [10, 20, 100]})


def test_duplicate_matching_service(test_db_path):
    """Verifies DuplicateMatchingService returns proper MatchDecision against SQLite state."""
    init_db(test_db_path)
    loc_svc = LocationService()
    dup_svc = DuplicateMatchingService(location_service=loc_svc)

    with get_db(test_db_path) as conn:
        conn.execute("DELETE FROM detections")
        conn.execute(
            """INSERT INTO detections
               (id, vehicle_id, latitude, longitude, severity, est_depth_cm,
                confidence, image_ref, timestamp, status, report_count)
               VALUES ('existing-inc-1', 'bus-1', 8.5241, 76.9366, 'minor', 2.0, 0.8, NULL, 1000.0, 'reported', 1)"""
        )

        # Coordinate within 4 meters
        match_close = dup_svc.evaluate_report_against_existing(conn, 8.52413, 76.9366)
        assert match_close.candidate_incident_id == "existing-inc-1"
        assert match_close.verdict in (MatchVerdict.EXACT_DUPLICATE, MatchVerdict.PROBABLE_MATCH)
        assert match_close.spatial_distance_m <= 5.0

        # Coordinate 200 meters away
        match_far = dup_svc.evaluate_report_against_existing(conn, 8.5260, 76.9366)
        assert match_far.candidate_incident_id is None
        assert match_far.verdict == MatchVerdict.DISTINCT_INCIDENT
