"""
Tests for Supabase Auth Verification Endpoint
=============================================
Tests /api/v1/auth/supabase-verify for Google OAuth session validation and profile mapping.
"""

import pytest


def test_supabase_verify_missing_token_returns_400(client):
    res = client.post("/api/v1/auth/supabase-verify", json={})
    assert res.status_code == 400
    data = res.get_json()
    assert data["code"] == "MISSING_TOKEN"


def test_supabase_verify_provisions_citizen_safely(client):
    payload = {
        "access_token": "mock_token_citizen_12345",
        "target_portal": "citizen",
        "email": "new.google.citizen@example.com",
        "name": "Ananya Sharma",
    }
    res = client.post("/api/v1/auth/supabase-verify", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    user = data["user"]
    assert user["email"] == "new.google.citizen@example.com"
    assert user["role"] == "citizen"  # Server-enforced citizen role
    assert "report_defect" in user["permissions"]
    assert "token" in data


def test_supabase_verify_rejects_unauthorized_municipal_attempt(client):
    payload = {
        "access_token": "mock_token_unauthorized_official_999",
        "target_portal": "municipal",
        "email": "random.uninvited.citizen@example.com",
        "name": "Random Citizen",
    }
    res = client.post("/api/v1/auth/supabase-verify", json=payload)
    assert res.status_code == 403
    data = res.get_json()
    assert data["code"] == "ACCESS_DENIED"
    assert "authorized municipal access" in data["error"]
