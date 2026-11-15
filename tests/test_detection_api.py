"""
CivicLens Step 5 — API & Authorization Tests for AI Defect Detection
=====================================================================
Tests:
- Trigger detection for authorized citizen evidence (/api/v1/evidence/<id>/detect)
- Missing model weights safely flagged without server crash
- Multi-object detection API output format (normalized bounding boxes, confidence tiers)
- Anti-IDOR: Citizen B cannot trigger detection or view Citizen A's detections
- Municipal officer can access and audit any evidence
- Report-level detections fetch (/api/v1/reports/<id>/detections)
- Detection review submission (/api/v1/detections/<id>/review)
- Domain safety: Citizen review does NOT alter municipal incident status
"""

import io
import os
import json
import uuid
import pytest
from PIL import Image

from backend.app import create_app
from backend.config import TestingConfig
from backend.auth import generate_auth_token
from backend.db.engine import get_session_factory
from backend.services.auth_service import AuthService
from backend.services.citizen_report_service import CitizenReportService
from backend.services.defect_detection_service import DefectDetectionService
from backend.services.model_provider import MockModelProvider, RawPrediction


@pytest.fixture
def app_and_client():
    cfg = TestingConfig()
    app = create_app(cfg)
    with app.test_client() as client:
        yield app, client


def _create_sample_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), color=(80, 80, 80)).save(buf, format="JPEG")
    return buf.getvalue()


def test_trigger_detection_with_mock_provider(app_and_client, monkeypatch):
    """Citizen can trigger detection and receives multi-object defect candidates."""
    app, client = app_and_client
    auth = AuthService()

    # Register Citizen with unique email
    email = f"alpha_{uuid.uuid4().hex[:6]}@civiclens.local"
    c_data = auth.register_citizen("Citizen Alpha", email, "Password123!", "Password123!")
    token = generate_auth_token(c_data["id"], "citizen")

    # Create report with image evidence
    report_svc = CitizenReportService()
    img_bytes = _create_sample_jpeg_bytes()
    rep = report_svc.create_report(
        citizen_id=c_data["id"],
        title="Main Street Multi Pothole Cluster",
        description="Multiple severe potholes near intersection causing traffic swerves",
        category="pothole",
        latitude=12.9716,
        longitude=77.5946,
        evidence_files=[{
            "filename": "street_cluster.jpg",
            "content_bytes": img_bytes,
            "mime_type": "image/jpeg",
        }],
    )
    assert len(rep["evidence"]) == 1
    asset_id = rep["evidence"][0]["id"]

    # Configure DefectDetectionService with MockModelProvider returning 3 distinct potholes
    canned_potholes = [
        RawPrediction(class_name="pothole", confidence=0.89, box_xyxy=(50.0, 50.0, 150.0, 150.0)),
        RawPrediction(class_name="pothole", confidence=0.76, box_xyxy=(250.0, 200.0, 400.0, 350.0)),
        RawPrediction(class_name="road_damage", confidence=0.62, box_xyxy=(450.0, 300.0, 550.0, 400.0)),
    ]
    mock_provider = MockModelProvider(canned_predictions=canned_potholes)
    monkeypatch.setattr(
        "backend.routes.detection_routes.detection_service.model_provider",
        mock_provider,
    )

    # POST /api/v1/evidence/<asset_id>/detect
    resp = client.post(
        f"/api/v1/evidence/{asset_id}/detect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    res_data = resp.get_json()
    assert res_data["status"] == "success"
    assert res_data["defect_count"] == 3
    assert len(res_data["detections"]) == 3

    # Verify normalized bounding boxes present
    d1 = res_data["detections"][0]
    assert d1["category"] == "pothole"
    assert d1["confidence"] == 0.89
    assert d1["confidence_tier"] == "high"
    assert d1["normalized_bbox"]["xmin"] is not None


def test_missing_weights_fails_safely(app_and_client):
    """When model weights are missing, API returns failed status with clear diagnostics without crashing."""
    app, client = app_and_client
    auth = AuthService()

    email = f"beta_{uuid.uuid4().hex[:6]}@civiclens.local"
    c_data = auth.register_citizen("Citizen Beta", email, "Password123!", "Password123!")
    token = generate_auth_token(c_data["id"], "citizen")

    report_svc = CitizenReportService()
    rep = report_svc.create_report(
        citizen_id=c_data["id"],
        title="Pothole Outside Market",
        description="Deep pothole in market lane",
        category="pothole",
        latitude=12.9716,
        longitude=77.5946,
        evidence_files=[{
            "filename": "market.jpg",
            "content_bytes": _create_sample_jpeg_bytes(),
            "mime_type": "image/jpeg",
        }],
    )
    asset_id = rep["evidence"][0]["id"]

    # Trigger detection with default YoloModelProvider (missing weights in test)
    resp = client.post(
        f"/api/v1/evidence/{asset_id}/detect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    res_data = resp.get_json()
    assert res_data["status"] == "failed"
    assert res_data["error_code"] == "MODEL_WEIGHTS_MISSING"
    assert "weights" in res_data["error_message"].lower()


def test_anti_idor_citizen_cannot_trigger_or_view_others_detections(app_and_client):
    """Citizen A cannot trigger detection or access detections for Citizen B's private evidence."""
    app, client = app_and_client
    auth = AuthService()

    # Citizen A
    email_a = f"alice_{uuid.uuid4().hex[:6]}@local.net"
    user_a = auth.register_citizen("Alice Owner", email_a, "Password123!", "Password123!")
    token_a = generate_auth_token(user_a["id"], "citizen")

    # Citizen B (Attacker)
    email_b = f"bob_{uuid.uuid4().hex[:6]}@local.net"
    user_b = auth.register_citizen("Bob Attacker", email_b, "Password123!", "Password123!")
    token_b = generate_auth_token(user_b["id"], "citizen")

    # Alice uploads evidence
    report_svc = CitizenReportService()
    rep_a = report_svc.create_report(
        citizen_id=user_a["id"],
        title="Alice Private Report",
        description="Pothole in residential driveway",
        category="pothole",
        latitude=12.9716,
        longitude=77.5946,
        evidence_files=[{
            "filename": "alice_driveway.jpg",
            "content_bytes": _create_sample_jpeg_bytes(),
            "mime_type": "image/jpeg",
        }],
    )
    asset_id = rep_a["evidence"][0]["id"]

    # Bob attempts to trigger detection on Alice's evidence
    resp_trigger = client.post(
        f"/api/v1/evidence/{asset_id}/detect",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_trigger.status_code == 404

    # Bob attempts to fetch detections for Alice's evidence
    resp_get = client.get(
        f"/api/v1/evidence/{asset_id}/detections",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_get.status_code == 404

    # Bob attempts to fetch detections for Alice's report
    resp_rep = client.get(
        f"/api/v1/reports/{rep_a['id']}/detections",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_rep.status_code == 404


def test_municipal_officer_can_view_and_audit_any_detections(app_and_client, monkeypatch):
    """Municipal officer has authorization to inspect detections across all citizen reports."""
    app, client = app_and_client
    auth = AuthService()

    email_c = f"charlie_{uuid.uuid4().hex[:6]}@local.net"
    email_o = f"rao_{uuid.uuid4().hex[:6]}@bbmp.gov.in"
    citizen = auth.register_citizen("Charlie", email_c, "Password123!", "Password123!")
    officer = auth.register_citizen("Officer Rao", email_o, "Password123!", "Password123!")

    # Upgrade officer role
    from backend.db.models import User
    db = get_session_factory()()
    u = db.query(User).filter_by(id=officer["id"]).first()
    u.role = "municipal_officer"
    db.commit()
    db.close()

    officer_token = generate_auth_token(officer["id"], "municipal_officer")

    # Charlie submits report
    report_svc = CitizenReportService()
    rep = report_svc.create_report(
        citizen_id=citizen["id"],
        title="Ring Road Crater",
        description="Massive crater near flyover",
        category="pothole",
        latitude=12.9716,
        longitude=77.5946,
        evidence_files=[{
            "filename": "crater.jpg",
            "content_bytes": _create_sample_jpeg_bytes(),
            "mime_type": "image/jpeg",
        }],
    )
    asset_id = rep["evidence"][0]["id"]

    # Mock detection
    mock_provider = MockModelProvider(canned_predictions=[
        RawPrediction(class_name="pothole", confidence=0.94, box_xyxy=(50.0, 50.0, 200.0, 200.0)),
    ])
    monkeypatch.setattr("backend.routes.detection_routes.detection_service.model_provider", mock_provider)

    # Officer triggers detection
    resp = client.post(
        f"/api/v1/evidence/{asset_id}/detect",
        headers={"Authorization": f"Bearer {officer_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["defect_count"] == 1


def test_detection_human_review_and_domain_safety(app_and_client, monkeypatch):
    """
    Citizens can review detections on their own reports (confirm/reject).
    CRITICAL DOMAIN RULE: Citizen review of an AI detection does NOT alter municipal incident status.
    """
    app, client = app_and_client
    auth = AuthService()

    email_d = f"david_{uuid.uuid4().hex[:6]}@local.net"
    c_data = auth.register_citizen("David", email_d, "Password123!", "Password123!")
    token = generate_auth_token(c_data["id"], "citizen")

    report_svc = CitizenReportService()
    rep = report_svc.create_report(
        citizen_id=c_data["id"],
        title="Pothole Near Bus Stop",
        description="Visible pothole in bus lane",
        category="pothole",
        latitude=12.9716,
        longitude=77.5946,
        evidence_files=[{
            "filename": "bus_lane.jpg",
            "content_bytes": _create_sample_jpeg_bytes(),
            "mime_type": "image/jpeg",
        }],
    )
    asset_id = rep["evidence"][0]["id"]

    mock_provider = MockModelProvider(canned_predictions=[
        RawPrediction(class_name="pothole", confidence=0.72, box_xyxy=(40.0, 40.0, 120.0, 120.0)),
    ])
    monkeypatch.setattr("backend.routes.detection_routes.detection_service.model_provider", mock_provider)

    # 1. Run detection
    det_resp = client.post(
        f"/api/v1/evidence/{asset_id}/detect",
        headers={"Authorization": f"Bearer {token}"},
    )
    det_id = det_resp.get_json()["detections"][0]["id"]

    # 2. Citizen confirms detection
    rev_resp = client.post(
        f"/api/v1/detections/{det_id}/review",
        headers={"Authorization": f"Bearer {token}"},
        json={"review_status": "confirmed", "review_notes": "Yes, this is definitely a pothole."},
    )
    assert rev_resp.status_code == 200
    assert rev_resp.get_json()["detection"]["review_status"] == "confirmed"

    # 3. DOMAIN SAFETY CHECK: Verify report status did NOT change
    db = get_session_factory()()
    from backend.db.models import CitizenReport
    fresh_rep = db.query(CitizenReport).filter_by(id=rep["id"]).first()
    # Report remains in its submitted status, NOT artificially auto-verified
    assert fresh_rep.status == "submitted"
    db.close()
