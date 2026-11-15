"""
Configuration Test Suite
========================

Verifies configuration loading, safe defaults, Supabase PostgreSQL validation,
URL normalization, secret redaction, and safe failure on invalid settings.
"""

import os
import pytest
from backend.config import (
    Config,
    TestingConfig,
    DevelopmentConfig,
    ProductionConfig,
    ConfigurationError,
    get_config,
    _resolve_db_path,
    normalize_database_url,
    redact_secret,
)


def test_invalid_port_fails_safely(monkeypatch):
    """Invalid port numbers (out of range or non-numeric) fail safely."""
    monkeypatch.setenv("PORT", "99999")
    with pytest.raises(ConfigurationError, match="PORT must be between 1 and 65535"):
        Config()

    monkeypatch.setenv("PORT", "invalid_number")
    with pytest.raises(ConfigurationError, match="Invalid PORT value"):
        Config()


def test_invalid_dedup_radius_fails_safely(monkeypatch):
    """Non-positive deduplication radius fails safely."""
    monkeypatch.setenv("DEDUP_RADIUS_METERS", "-5.0")
    with pytest.raises(ConfigurationError, match="DEDUP_RADIUS_METERS must be greater than 0"):
        Config()


def test_production_without_secret_key_fails_safely(monkeypatch):
    """In production, missing, default, or short secret key fails safely."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.setenv("SECRET_KEY", "insecure-dev-key-civiclens-change-in-production")
    with pytest.raises(ConfigurationError, match="SECRET_KEY must be explicitly set"):
        ProductionConfig()

    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(ConfigurationError, match="min 32 characters"):
        ProductionConfig()


def test_production_with_flask_debug_fails_safely(monkeypatch):
    """Production configuration must never allow FLASK_DEBUG=1."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("FLASK_DEBUG", "1")
    with pytest.raises(ConfigurationError, match="FLASK_DEBUG cannot be enabled in production"):
        ProductionConfig()


def test_db_path_resolution():
    """Verifies SQLite database path resolution across different invocations."""
    assert _resolve_db_path(":memory:") == ":memory:"
    assert _resolve_db_path("/tmp/custom.db") == "/tmp/custom.db"
    resolved = _resolve_db_path("backend/pothole_reports.db")
    assert resolved.endswith("pothole_reports.db")


def test_supabase_provider_without_database_url_fails_safely(monkeypatch):
    """Selecting supabase as provider without DATABASE_URL raises ConfigurationError."""
    monkeypatch.setenv("DATABASE_PROVIDER", "supabase")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigurationError, match="DATABASE_URL is missing or empty"):
        Config()


def test_supabase_provider_with_placeholder_credentials_fails_safely(monkeypatch):
    """Providing a placeholder connection string fails safely rather than trying to connect."""
    monkeypatch.setenv("DATABASE_PROVIDER", "supabase")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:YOUR_PASSWORD@db.YOUR_SUPABASE.co:5432/postgres")
    with pytest.raises(ConfigurationError, match="contains placeholder values"):
        Config()


def test_unsupported_database_provider_fails_safely(monkeypatch):
    """Specifying an unknown database provider fails safely."""
    monkeypatch.setenv("DATABASE_PROVIDER", "mongodb")
    with pytest.raises(ConfigurationError, match="Unsupported DATABASE_PROVIDER"):
        Config()


def test_normalize_database_url():
    """Verifies postgres:// conversion and sslmode enforcement for remote Supabase connections."""
    # Convert postgres:// to postgresql://
    res = normalize_database_url("postgres://user:pass@aws-0.pooler.supabase.com:6543/postgres")
    assert res.startswith("postgresql://")
    assert "sslmode=require" in res

    # Localhost should not force sslmode
    res_local = normalize_database_url("postgresql://user:pass@localhost:5432/testdb")
    assert "sslmode" not in res_local

    # None should return None
    assert normalize_database_url(None) is None


def test_redact_secret():
    """Verifies secret values are redacted for logs without exposing sensitive tokens."""
    secret = "f097fffb474f4ae3bc82d1aa4235ff81"
    redacted = redact_secret(secret, show_chars=4)
    assert redacted.startswith("f097...")
    assert redacted.endswith("ff81 (len=32)")
    assert "474f4ae3bc82d1aa" not in redacted
    assert redact_secret(None) == "[NOT SET]"


def test_max_content_length_mb_conversion(monkeypatch):
    """MAX_CONTENT_LENGTH_MB is converted into bytes correctly."""
    monkeypatch.setenv("MAX_CONTENT_LENGTH_MB", "32")
    cfg = Config()
    assert cfg.MAX_CONTENT_LENGTH == 32 * 1024 * 1024
    assert cfg.MAX_CONTENT_LENGTH_MB == 32
