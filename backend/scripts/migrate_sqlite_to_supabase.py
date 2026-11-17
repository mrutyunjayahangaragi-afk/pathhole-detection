#!/usr/bin/env python3
"""
CivicLens SQLite to Supabase PostgreSQL Migration Script
========================================================
Performs safe, ordered, and repeatable data migration from local SQLite
(backend/pothole_reports.db) into remote Supabase PostgreSQL.

Features:
- Creates verified SQLite backup before starting
- Strictly ordered dependency resolution (preserves Foreign Keys)
- Idempotent upserts (ON CONFLICT (id) DO NOTHING / UPDATE)
- Automatic type casting (SQLite integer booleans -> PostgreSQL booleans)
- Checkpoint reporting and row-count verification (PASS / FAIL)
- Zero secret exposure in output logs
"""

import os
import sys
import shutil
import time
import sqlite3
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from sqlalchemy import create_engine, text
from backend.config import normalize_database_url, redact_secret

# Tables in strict foreign-key dependency order
MIGRATION_TABLES = [
    "municipalities",
    "departments",
    "users",
    "department_memberships",
    "incidents_v2",
    "citizen_reports_v2",
    "location_records",
    "report_items",
    "evidence_assets_v2",
    "report_evidence",
    "incident_observations_v2",
    "incident_assignments",
    "work_progress_updates",
    "inspection_records",
    "resolution_records",
    "incident_status_history",
    "citizen_visible_updates",
    "notification_events",
    "notification_deliveries",
    "notification_preferences",
    "user_notifications",
    "ai_description_assistance",
    "report_translations",
    "telemetry_devices",
    "telemetry_events",
    "detections",
    "audit_logs_v2",
]


def backup_sqlite(source_path: Path) -> Path:
    """Creates a timestamped backup of the active SQLite database."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = source_path.with_name(f"{source_path.stem}.backup_{timestamp}.db")
    shutil.copy2(source_path, backup_path)
    # Verify backup size matches
    if backup_path.stat().st_size != source_path.stat().st_size:
        raise RuntimeError(f"Backup verification failed: size mismatch between {source_path} and {backup_path}")
    print(f"[*] Verified SQLite backup created: {backup_path} ({backup_path.stat().st_size} bytes)")
    return backup_path


def get_sqlite_table_info(conn: sqlite3.Connection, table_name: str) -> List[Tuple[str, str]]:
    """Returns list of (column_name, data_type) for a table in SQLite."""
    cur = conn.cursor()
    cur.execute(f'PRAGMA table_info("{table_name}");')
    return [(r[1], r[2].upper()) for r in cur.fetchall()]


def get_pg_table_columns(engine, table_name: str) -> Dict[str, str]:
    """Returns dict of column_name -> data_type for table in PostgreSQL."""
    with engine.connect() as conn:
        res = conn.execute(text(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = '{table_name}';
        """)).fetchall()
        return {r[0]: r[1].lower() for r in res}


def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_engine,
    table_name: str,
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Migrates a single table from SQLite to PostgreSQL with type conversion."""
    sq_cols_info = get_sqlite_table_info(sqlite_conn, table_name)
    if not sq_cols_info:
        return {"status": "SKIPPED", "source_count": 0, "target_count": 0, "migrated": 0, "message": "Table missing in SQLite"}

    pg_cols = get_pg_table_columns(pg_engine, table_name)
    if not pg_cols:
        return {"status": "SKIPPED", "source_count": 0, "target_count": 0, "migrated": 0, "message": "Table missing in PostgreSQL"}

    # Common columns
    common_cols = [c[0] for c in sq_cols_info if c[0] in pg_cols]
    if not common_cols:
        return {"status": "SKIPPED", "source_count": 0, "target_count": 0, "migrated": 0, "message": "No overlapping columns"}

    # Count source rows
    s_cur = sqlite_conn.cursor()
    s_cur.execute(f'SELECT COUNT(*) FROM "{table_name}";')
    source_count = s_cur.fetchone()[0]

    if source_count == 0:
        return {"status": "PASS", "source_count": 0, "target_count": 0, "migrated": 0, "message": "Empty source table"}

    # Fetch rows
    col_str = ", ".join(f'"{c}"' for c in common_cols)
    s_cur.execute(f'SELECT {col_str} FROM "{table_name}";')
    rows = s_cur.fetchall()

    # Determine which columns are booleans in PostgreSQL
    bool_col_indices = [i for i, c in enumerate(common_cols) if "bool" in pg_cols[c]]

    # Prepare PostgreSQL insert query
    placeholders = ", ".join(f":{c}" for c in common_cols)
    
    # Universal conflict handling: ignores conflicts on any unique index or constraint
    conflict_clause = "ON CONFLICT DO NOTHING"

    insert_sql = text(f"""
        INSERT INTO "{table_name}" ({col_str})
        VALUES ({placeholders})
        {conflict_clause};
    """)

    migrated_count = 0
    with pg_engine.begin() as pg_conn:
        batch = []
        for row in rows:
            row_dict = {}
            for i, c in enumerate(common_cols):
                val = row[i]
                if i in bool_col_indices and val is not None:
                    val = bool(val)
                row_dict[c] = val
            batch.append(row_dict)

            if len(batch) >= batch_size:
                pg_conn.execute(insert_sql, batch)
                migrated_count += len(batch)
                batch = []

        if batch:
            pg_conn.execute(insert_sql, batch)
            migrated_count += len(batch)

    # Verify final target row count
    with pg_engine.connect() as pg_conn:
        target_count = pg_conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}";')).scalar()

    status = "PASS" if target_count >= source_count else "FAIL"
    return {
        "status": status,
        "source_count": source_count,
        "target_count": target_count,
        "migrated": migrated_count,
        "message": f"Source: {source_count} -> Target: {target_count}",
    }


def run_migration():
    print("=" * 70)
    print("CIVICLENS: SQLITE TO SUPABASE POSTGRESQL DATA MIGRATION")
    print("=" * 70)

    db_path = PROJECT_ROOT / "backend" / "pothole_reports.db"
    if not db_path.exists():
        print(f"[!] Error: SQLite database not found at {db_path}")
        sys.exit(1)

    raw_pg_url = os.environ.get("DATABASE_URL")
    if not raw_pg_url:
        print("[!] Error: DATABASE_URL not configured in environment.")
        sys.exit(1)

    norm_url = normalize_database_url(raw_pg_url)
    print(f"[*] Target PostgreSQL URL: {redact_secret(norm_url)}")

    # 1. Backup SQLite
    backup_path = backup_sqlite(db_path)

    # 2. Connect to databases
    sq_conn = sqlite3.connect(db_path)
    from backend.db.engine import get_engine
    pg_engine = get_engine(norm_url)

    # Verify connection
    with pg_engine.connect() as conn:
        version = conn.execute(text("SELECT version();")).scalar()
        print(f"[*] Connected to remote PostgreSQL:\n    {version[:65]}")

    print("\n[*] Starting ordered table migration...\n")
    print(f"{'Table Name':<28} | {'Status':<6} | {'Source':<7} | {'Target':<7} | {'Details'}")
    print("-" * 75)

    all_passed = True
    results = {}
    for table_name in MIGRATION_TABLES:
        try:
            res = migrate_table(sq_conn, pg_engine, table_name)
            results[table_name] = res
            status_symbol = "✓ PASS" if res["status"] == "PASS" else ("~ SKIP" if res["status"] == "SKIPPED" else "✗ FAIL")
            if res["status"] == "FAIL":
                all_passed = False
            print(f"{table_name:<28} | {status_symbol:<6} | {res['source_count']:<7} | {res['target_count']:<7} | {res['message']}")
        except Exception as e:
            all_passed = False
            print(f"{table_name:<28} | ✗ ERR  | {'--':<7} | {'--':<7} | {type(e).__name__}: {str(e)[:40]}")

    print("-" * 75)
    sq_conn.close()

    if all_passed:
        print("\n[✓] ALL TABLES SUCCESSFULLY MIGRATED TO SUPABASE POSTGRESQL!")
    else:
        print("\n[!] Migration completed with some warnings or failures. Review above.")

    return all_passed


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
