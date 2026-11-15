"""
Configuration Test Suite
========================

Verifies configuration loading, safe defaults, and safe failure on invalid settings.
"""

import os
import pytest
from backend.config import (
    Config,
    TestingConfig,
    ProductionConfig,
    ConfigurationError,
    get_config,
    _resolve_db_path,
)


def test_invalid_port_fails_safely(monkeypatch):
    """Rule 7: Invalid configuration (e.g., negative or out-of-range port) fails safely."""
    monkeypatch.setenv("PORT", "99999")
    with pytest.raises(ConfigurationError, match="PORT must be between 1 and 65535"):
        Config()

    monkeypatch.setenv("PORT", "invalid_number")
    with pytest.raises(ConfigurationError, match="Invalid PORT value"):
        Config()


def test_invalid_dedup_radius_fails_safely(monkeypatch):
    """Rule 7: Non-positive deduplication radius fails safely."""
    monkeypatch.setenv("DEDUP_RADIUS_METERS", "-5.0")
    with pytest.raises(ConfigurationError, match="DEDUP_RADIUS_METERS must be greater than 0"):
        Config()


def test_production_without_secret_key_fails_safely(monkeypatch):
    """Rule 7: In production, missing or default secret key fails safely."""
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "insecure-dev-key-civiclens-change-in-production")
    with pytest.raises(ConfigurationError, match="SECRET_KEY must be explicitly set"):
        ProductionConfig()


def test_db_path_resolution():
    """Verifies SQLite database path resolution across different invocations."""
    # Memory string should pass through unchanged
    assert _resolve_db_path(":memory:") == ":memory:"
    
    # Absolute path should pass through
    assert _resolve_db_path("/tmp/custom.db") == "/tmp/custom.db"
    
    # Existing backend path should resolve cleanly
    resolved = _resolve_db_path("backend/pothole_reports.db")
    assert resolved.endswith("pothole_reports.db")
