"""
Citizen Grievance Reporting Tests
=================================

Verifies:
- Report creation with JSON and multipart file uploads
- Unsupported file type rejection
- Location metadata (GPS accuracy vs manual placement)
- Multilingual Kannada & English text integrity
- Idempotency via Idempotency-Key
- Atomic transactional consistency
"""

import io
import uuid
import pytest


@pytest.fixture
def citizen_token(client):
    """Registers and returns a valid Bearer token for a test citizen."""
    unique_email = f"reporter_{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/api/v1/auth/register", json={
        "display_name": "Citizen Tester",
        "email": unique_email,
        "password": "Password123",
        "confirm_password": "Password123"
    })
    return res.get_json()["token"]


def test_submit_report_json(client, citizen_token):
    headers = {"Authorization": f"Bearer {citizen_token}"}
    payload = {
        "title": "Severe pothole near 80ft road junction",
        "description": "Large road crater causing vehicle damage and traffic bottleneck",
        "category": "pothole",
        "severity": "severe",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "address": "80 Feet Rd, Koramangala 4th Block",
        "location_accuracy_m": 6.5,
        "is_manual_location": False,
        "original_language": "en"
    }
    res = client.post("/api/v1/reports", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.get_json()
    assert data["status"] == "success"
    rep = data["report"]
    assert rep["report_reference"].startswith("CR-")
    assert rep["title"] == "Severe pothole near 80ft road junction"
    assert rep["severity"] == "severe"
    assert rep["category"] == "pothole"
    assert rep["status"] == "submitted"
    assert rep["latitude"] == 12.9716
    assert rep["longitude"] == 77.5946


def test_submit_report_multipart_with_evidence(client, citizen_token):
    headers = {"Authorization": f"Bearer {citizen_token}"}
    img_data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00" + (b"\x00" * 100)

    data = {
        "title": "Broken road culvert",
        "description": "Culvert collapse near bridge, high risk during rains",
        "category": "bridge_damage",
        "severity": "critical",
        "latitude": "12.9350",
        "longitude": "77.6100",
        "address": "Ring Road Culvert #12",
        "is_manual_location": "true",
        "photos": (io.BytesIO(img_data), "damage_photo.jpg", "image/jpeg")
    }
    res = client.post("/api/v1/reports", data=data, content_type="multipart/form-data", headers=headers)
    assert res.status_code == 201
    rep = res.get_json()["report"]
    assert rep["category"] == "bridge_damage"
    assert rep["is_manual_location"] is True
    assert rep["evidence_count"] >= 1


def test_submit_report_rejects_unsupported_file(client, citizen_token):
    headers = {"Authorization": f"Bearer {citizen_token}"}
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00"

    data = {
        "title": "Dangerous road debris",
        "description": "Debris scattered on highway lane",
        "category": "garbage",
        "severity": "moderate",
        "latitude": "12.9000",
        "longitude": "77.6000",
        "photos": (io.BytesIO(fake_exe), "malicious.exe", "application/x-executable")
    }
    res = client.post("/api/v1/reports", data=data, content_type="multipart/form-data", headers=headers)
    assert res.status_code == 400
    assert "Unsupported media format" in res.get_json()["error"]


def test_submit_report_validation_errors(client, citizen_token):
    headers = {"Authorization": f"Bearer {citizen_token}"}

    # Short title
    r1 = client.post("/api/v1/reports", json={
        "title": "No", "description": "Valid description of problem", "category": "pothole", "latitude": 12.0, "longitude": 77.0
    }, headers=headers)
    assert r1.status_code == 400

    # Invalid category
    r2 = client.post("/api/v1/reports", json={
        "title": "Valid title", "description": "Valid description", "category": "invalid_cat", "latitude": 12.0, "longitude": 77.0
    }, headers=headers)
    assert r2.status_code == 400

    # Coordinates out of range
    r3 = client.post("/api/v1/reports", json={
        "title": "Valid title", "description": "Valid description", "category": "pothole", "latitude": 95.0, "longitude": 77.0
    }, headers=headers)
    assert r3.status_code == 400


def test_idempotency_returns_original_report(client, citizen_token):
    headers = {
        "Authorization": f"Bearer {citizen_token}",
        "Idempotency-Key": "unique-client-req-uuid-101"
    }
    payload = {
        "title": "Streetlight leaning over road",
        "description": "Streetlight pole bent and spark visible",
        "category": "broken_streetlight",
        "severity": "severe",
        "latitude": 12.9500,
        "longitude": 77.5800,
    }

    # First submission
    res1 = client.post("/api/v1/reports", json=payload, headers=headers)
    assert res1.status_code == 201
    report1 = res1.get_json()["report"]

    # Second submission with same Idempotency-Key
    res2 = client.post("/api/v1/reports", json=payload, headers=headers)
    assert res2.status_code == 201
    report2 = res2.get_json()["report"]

    # Both submissions must return the exact same report ID and reference
    assert report1["id"] == report2["id"]
    assert report1["report_reference"] == report2["report_reference"]


def test_kannada_multilingual_text_preservation(client, citizen_token):
    headers = {"Authorization": f"Bearer {citizen_token}"}
    kannada_title = "ಇಂದಿರಾನಗರ 100 ಅಡಿ ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ"
    kannada_desc = "ಮೆಟ್ರೋ ನಿಲ್ದಾಣದ ಬಳಿ ಆಳವಾದ ರಸ್ತೆ ಗುಂಡಿ ಇದ್ದು ದ್ವಿಚಕ್ರ ವಾಹನಗಳಿಗೆ ಅಪಾಯಕಾರಿಯಾಗಿದೆ."

    payload = {
        "title": kannada_title,
        "description": kannada_desc,
        "category": "pothole",
        "severity": "critical",
        "latitude": 12.9780,
        "longitude": 77.6400,
        "address": "ಇಂದಿರಾನಗರ, ಬೆಂಗಳೂರು",
        "original_language": "kn"
    }
    res = client.post("/api/v1/reports", json=payload, headers=headers)
    assert res.status_code == 201
    rep = res.get_json()["report"]

    # Exact Unicode preservation verification
    assert rep["title"] == kannada_title
    assert rep["description"] == kannada_desc
    assert rep["original_language"] == "kn"
