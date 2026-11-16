"""
Tests for Supabase Migrations Idempotency
=========================================
Verifies that all migration files in supabase/migrations/ are well-formed and idempotent.
"""

from pathlib import Path


def test_supabase_migrations_directory_and_files_exist():
    migrations_dir = Path("supabase/migrations")
    assert migrations_dir.exists() and migrations_dir.is_dir()

    sql_files = sorted(list(migrations_dir.glob("*.sql")))
    assert len(sql_files) >= 6

    # Verify each migration file contains IF NOT EXISTS / idempotent DDL
    for sql_file in sql_files:
        content = sql_file.read_text()
        assert len(content.strip()) > 50
        # Should not have raw non-idempotent CREATE TABLE without IF NOT EXISTS
        if "CREATE TABLE" in content:
            assert "CREATE TABLE IF NOT EXISTS" in content


def test_supabase_seed_file_is_idempotent():
    seed_file = Path("supabase/seed.sql")
    assert seed_file.exists()
    content = seed_file.read_text()
    assert "ON CONFLICT" in content
    assert "BBMP" in content
    assert "ROAD_MAINT" in content
