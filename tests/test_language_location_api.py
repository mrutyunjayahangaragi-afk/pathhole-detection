"""
Tests for Language and Location REST APIs
=========================================
Tests endpoints for language detection, translation, assistance,
reverse geocoding, and context retrieval.
"""

import uuid
from unittest.mock import patch, MagicMock
import pytest
from backend.app import create_app
from backend.config import TestingConfig
from backend.services.auth_service import AuthService
from backend.services.citizen_report_service import CitizenReportService


@pytest.fixture
def citizen_token(client):
    uid = uuid.uuid4().hex[:6]
    res = client.post("/api/v1/auth/register", json={
        "display_name": f"API User {uid}",
        "email": f"api_user_{uid}@example.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
    })
    return res.get_json()["token"]


def test_api_language_detection(client):
    # Public endpoint
    resp = client.post("/api/v1/language/detect", json={
        "text": "ನಮ್ಮ ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಇದೆ"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["detection"]["detected_language"] == "kn"
    assert data["detection"]["confidence"] >= 0.80


def test_api_language_translation(client):
    # Public endpoint
    resp = client.post("/api/v1/language/translate", json={
        "text": "ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಬಿದ್ದಿದೆ",
        "source_language": "kn",
        "target_language": "en",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert "pothole" in data["translation"]["translated_text"].lower()


def test_api_description_assistance(client, citizen_token):
    # Authenticated endpoint
    resp = client.post(
        "/api/v1/language/assist",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "text": "Deep crater pothole near Indiranagar metro station pillar 14 causing hazard.",
            "language": "en",
            "has_location": True,
            "has_evidence": True,
        }
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["suggested_category"] == "pothole"
    assert len(data["summary"]) > 0


def test_api_location_reverse_geocode(client):
    mock_payload = {
        "display_name": "MG Road, Bengaluru, Karnataka, 560001, India",
        "type": "primary",
        "address": {
            "road": "MG Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postcode": "560001",
            "country": "India"
        }
    }

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        resp = client.post("/api/v1/location/reverse-geocode", json={
            "latitude": 12.9756,
            "longitude": 77.6066,
            "language": "en"
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["location"]["road_name"] == "MG Road"
        assert data["location"]["city"] == "Bengaluru"


def test_api_report_translations_and_context(client, citizen_token):
    # Create report first
    rep_resp = client.post(
        "/api/v1/reports",
        headers={"Authorization": f"Bearer {citizen_token}"},
        json={
            "title": "ರಸ್ತೆ ಸಮಸ್ಯೆ",
            "description": "ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಬಿದ್ದಿದೆ near bus stop",
            "category": "pothole",
            "severity": "moderate",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "original_language": "kn",
        }
    )
    assert rep_resp.status_code == 201
    rep_id = rep_resp.get_json()["report"]["id"]

    # Retrieve translations
    t_resp = client.get(
        f"/api/v1/language/translations/{rep_id}",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert t_resp.status_code == 200
    t_data = t_resp.get_json()
    assert t_data["status"] == "success"
    assert len(t_data["translations"]) >= 1

    # Retrieve location context
    loc_resp = client.get(
        f"/api/v1/location/context/{rep_id}",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert loc_resp.status_code == 200
    loc_data = loc_resp.get_json()
    assert loc_data["status"] == "success"
    assert loc_data["coordinates"]["latitude"] == 12.9716

    # Test multilingual search endpoint
    s_resp = client.get(
        "/api/v1/reports/search?q=ಗುಂಡಿ",
        headers={"Authorization": f"Bearer {citizen_token}"}
    )
    assert s_resp.status_code == 200
    s_data = s_resp.get_json()
    assert s_data["status"] == "success"
    assert s_data["total"] >= 1
