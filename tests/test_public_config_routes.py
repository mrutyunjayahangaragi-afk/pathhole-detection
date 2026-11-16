"""
Tests for Public Configuration Route
====================================
Verifies that /api/public/config delivers safe public Supabase credentials,
diagnostics, and caching headers without exposing any private secrets.
"""

import pytest


def test_public_config_success(client):
    res = client.get("/api/public/config")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "supabase_ready" in data
    assert "diagnostic_code" in data
    assert "supabase_url" in data
    assert "supabase_publishable_key" in data
    assert "app_name" in data
    assert res.headers.get("Cache-Control") == "public, max-age=60"


def test_public_config_never_leaks_secrets(client):
    res = client.get("/api/public/config")
    raw = res.get_data(as_text=True)

    # Privacy verification
    assert "DATABASE_URL" not in raw
    assert "postgresql://" not in raw
    assert "SUPABASE_SERVICE_ROLE_KEY" not in raw
    assert "service_role" not in raw
    assert "SECRET_KEY" not in raw
    assert "password" not in raw.lower()


def test_public_config_readiness_states(client):
    # Case 1: Unconfigured / Empty
    client.application.config["SUPABASE_URL"] = ""
    client.application.config["SUPABASE_PUBLISHABLE_KEY"] = ""

    res = client.get("/api/public/config")
    data = res.get_json()
    assert data["supabase_ready"] is False
    assert data["diagnostic_code"] == "MISSING_CONFIG"
    assert data["supabase_url"] == ""
    assert data["supabase_publishable_key"] == ""

    # Case 2: Configured with valid URL and publishable key
    client.application.config["SUPABASE_URL"] = "https://example-project.supabase.co"
    client.application.config["SUPABASE_PUBLISHABLE_KEY"] = "sb_publishable_valid_key_test123"

    res = client.get("/api/public/config")
    data = res.get_json()
    assert data["supabase_ready"] is True
    assert data["diagnostic_code"] == "READY"
    assert data["supabase_url"] == "https://example-project.supabase.co"
    assert data["supabase_publishable_key"] == "sb_publishable_valid_key_test123"

    # Case 3: Rejects secret keys being leaked
    client.application.config["SUPABASE_PUBLISHABLE_KEY"] = "sb_secret_should_never_leak"
    res = client.get("/api/public/config")
    data = res.get_json()
    assert data["supabase_ready"] is False
    assert data["supabase_publishable_key"] == ""
