"""
Supabase PostgreSQL Integration & Migration Safety Tests
=========================================================

Verifies:
- SQLite database integrity and non-destructive online backup creation.
- Supabase configuration validation (placeholder rejection, missing URL handling).
- Migration script safety in dry-run and verify-only modes.
- API health check dynamic database ping and provider reporting.
"""

import os
import sqlite3
import tempfile
import pytest
from pathlib import Path

from backend.config import get_config
from scripts.migrate_sqlite_to_supabase import (
    migrate_to_supabase,
    get_sqlite_table_counts,
    parse_datetime,
    parse_bool,
)


def test_sqlite_database_file_intact():
    """Verifies existing SQLite database file is present, has 106 detections, and passes integrity check."""
    db_path = "backend/pothole_reports.db"
    assert os.path.exists(db_path), f"Database file not found: {db_path}"

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("PRAGMA integrity_check;")
    res = c.fetchone()[0]
    assert res == "ok", f"Integrity check failed: {res}"

    c.execute("SELECT COUNT(*) FROM detections;")
    det_count = c.fetchone()[0]
    assert det_count >= 106, f"Expected at least 106 legacy detections, got {det_count}"
    conn.close()


def test_sqlite_consistent_backup_creation():
    """Verifies that an atomic online backup can be generated and queried without touching original DB."""
    src_db = "backend/pothole_reports.db"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        backup_path = tmp.name

    try:
        src_conn = sqlite3.connect(src_db)
        dst_conn = sqlite3.connect(backup_path)

        with dst_conn:
            src_conn.backup(dst_conn)

        dst_conn.close()
        src_conn.close()

        # Verify backup file
        assert os.path.getsize(backup_path) > 0
        verify_conn = sqlite3.connect(backup_path)
        c = verify_conn.cursor()
        c.execute("PRAGMA integrity_check;")
        assert c.fetchone()[0] == "ok"

        # Compare row counts
        src_counts = get_sqlite_table_counts(Path(src_db))
        dst_counts = get_sqlite_table_counts(Path(backup_path))
        assert src_counts == dst_counts
        verify_conn.close()
    finally:
        if os.path.exists(backup_path):
            os.remove(backup_path)


def test_migration_blocks_safely_when_target_missing(monkeypatch):
    """Migration script must return False and report BLOCKED when target DATABASE_URL is not provided."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    success, res = migrate_to_supabase(
        source_sqlite="backend/pothole_reports.db",
        target_url=None,
    )
    assert success is False
    assert any("DATABASE_URL is not configured" in err for err in res["errors"])


def test_migration_blocks_safely_on_placeholder_credentials():
    """Migration script must return False and report BLOCKED on placeholder credentials."""
    success, res = migrate_to_supabase(
        source_sqlite="backend/pothole_reports.db",
        target_url="postgresql://postgres:YOUR_PASSWORD@db.YOUR_SUPABASE.co:5432/postgres",
    )
    assert success is False
    assert any("placeholder credentials" in err for err in res["errors"])


def test_migration_dry_run_simulation(monkeypatch):
    """Verifies migration transformation and rollback simulation without writing data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        target_sqlite = tmp.name

    try:
        target_url = f"sqlite:///{target_sqlite}"
        success, res = migrate_to_supabase(
            source_sqlite="backend/pothole_reports.db",
            target_url=target_url,
            dry_run=True,
        )
        assert success is True
        assert res["status"] == "DRY_RUN_COMPLETED"
        assert res["dry_run"] is True
    finally:
        if os.path.exists(target_sqlite):
            os.remove(target_sqlite)


def test_type_parsers():
    """Verifies timestamp and boolean parser normalization."""
    # Datetime parser
    dt = parse_datetime(1700000000)
    assert dt is not None
    assert dt.year == 2023

    dt_iso = parse_datetime("2026-11-15T22:30:00Z")
    assert dt_iso is not None
    assert dt_iso.year == 2026

    assert parse_datetime(None) is None

    # Bool parser
    assert parse_bool(1) is True
    assert parse_bool(0) is False
    assert parse_bool("true") is True
    assert parse_bool("false") is False
    assert parse_bool(None) is False


def test_health_check_reports_database_provider(client):
    """Health check endpoint must report database provider and live connection status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "database_provider" in data
    assert data["database_provider"] in ("sqlite", "supabase", "postgresql")
    assert data["database_status"] == "connected"
