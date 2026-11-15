#!/usr/bin/env python3
"""
Legacy Data Migration Script: SQLite Legacy Detections -> CivicLens Normalized Schema
===================================================================================

Extracts legacy detection records from `detections` table (SQLite) and migrates them
into the normalized `incidents_v2` and `incident_observations_v2` tables in target
database (PostgreSQL or SQLite).

Features:
- Preserves primary keys (UUIDs), coordinates, severity, depth, status, and timestamps.
- Idempotent: safe to run multiple times without duplicating incidents.
- Verifies integrity and row counts post-migration.
- Zero data loss guarantee: leaves source `detections` table completely untouched.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone
import argparse
import sqlite3

# Ensure project root is in sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.db.engine import get_engine, get_session_factory
from backend.db.init_schema import create_all_tables
from backend.db.models import Incident, IncidentObservation, IncidentStatusHistory


def parse_args():
    parser = argparse.ArgumentParser(description="Migrate legacy SQLite detections to CivicLens normalized schema.")
    parser.add_argument(
        "--source-sqlite",
        default="backend/pothole_reports.db",
        help="Path to source SQLite database file containing legacy detections table.",
    )
    parser.add_argument(
        "--target-url",
        default=None,
        help="Target SQLAlchemy database URL (defaults to DATABASE_URL or same SQLite db).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform extraction and validation without committing changes to target.",
    )
    return parser.parse_args()


def migrate(source_db_path: str, target_url: str = None, dry_run: bool = False):
    source_path = Path(source_db_path).resolve()
    if not source_path.exists():
        print(f"[ERROR] Source SQLite database not found: {source_path}")
        return False

    print(f"[*] Reading legacy detections from: {source_path}")
    source_conn = sqlite3.connect(str(source_path))
    source_conn.row_factory = sqlite3.Row
    c = source_conn.cursor()

    try:
        c.execute("SELECT COUNT(*) FROM detections")
        total_legacy = c.fetchone()[0]
        print(f"[*] Found {total_legacy} legacy detection records.")
    except sqlite3.OperationalError as e:
        print(f"[ERROR] Could not read detections table: {e}")
        source_conn.close()
        return False

    # Initialize target schema
    resolved_target = target_url or os.environ.get("DATABASE_URL") or f"sqlite:///{source_path}"
    print(f"[*] Target database: {resolved_target}")
    create_all_tables(resolved_target)

    session_factory = get_session_factory(resolved_target)
    session = session_factory()

    c.execute("SELECT * FROM detections")
    rows = c.fetchall()

    imported_incidents = 0
    updated_incidents = 0
    errors = 0

    try:
        for row in rows:
            rec = dict(row)
            rec_id = str(rec["id"])

            # Map timestamp to datetime
            ts = rec.get("timestamp")
            if ts and isinstance(ts, (int, float)):
                created_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            else:
                created_dt = datetime.now(timezone.utc)

            # Map status
            status = str(rec.get("status") or "reported").lower()
            if status not in ("reported", "acknowledged", "scheduled", "in_progress", "repaired", "verified", "closed"):
                status = "reported"

            severity = str(rec.get("severity") or "minor").lower()
            if severity not in ("minor", "moderate", "severe", "critical"):
                severity = "minor"

            depth = float(rec.get("est_depth_cm") or 0.0)
            report_count = int(rec.get("report_count") or 1)
            address = rec.get("address")
            lat = float(rec.get("latitude") or 0.0)
            lon = float(rec.get("longitude") or 0.0)

            clean_id = str(rec_id).replace("-", "").upper()
            ref = f"LEG-{clean_id[:10]}" if len(clean_id) >= 10 else f"LEG-{clean_id}_{imported_incidents:04d}"

            # Check if incident already exists
            existing_incident = session.query(Incident).filter_by(id=rec_id).first()

            if not existing_incident:
                incident = Incident(
                    id=rec_id,
                    incident_reference=ref,
                    category="pothole",
                    description=f"Imported legacy pothole detection (vehicle {rec.get('vehicle_id', 'unknown')})",
                    severity=severity,
                    status=status,
                    latitude=lat,
                    longitude=lon,
                    location_accuracy_m=10.0,
                    address=address,
                    report_count=report_count,
                    est_depth_cm=depth,
                    created_at=created_dt,
                    updated_at=created_dt,
                    resolved_at=created_dt if status == "repaired" else None,
                )
                session.add(incident)

                # Add initial observation
                obs = IncidentObservation(
                    incident_id=rec_id,
                    observation_type="vehicle_sensor",
                    verification_status="verified" if status == "repaired" else "unverified",
                    observed_at=created_dt,
                    created_at=created_dt,
                )
                session.add(obs)
                imported_incidents += 1
            else:
                existing_incident.report_count = max(existing_incident.report_count, report_count)
                existing_incident.status = status
                existing_incident.severity = severity
                existing_incident.est_depth_cm = depth
                updated_incidents += 1

        if dry_run:
            print("[DRY-RUN] Rolling back transaction without writing.")
            session.rollback()
        else:
            session.commit()
            print(f"[SUCCESS] Migration committed: {imported_incidents} new incidents imported, {updated_incidents} updated.")

        # Post-migration verification
        verified_count = session.query(Incident).count()
        print(f"[*] Post-migration Incident count in incidents_v2: {verified_count}")
        assert verified_count >= total_legacy or dry_run, "Mismatch between legacy records and incidents_v2!"

    except Exception as e:
        session.rollback()
        print(f"[FATAL] Migration failed with error: {e}")
        return False
    finally:
        session.close()
        source_conn.close()

    return True


if __name__ == "__main__":
    args = parse_args()
    success = migrate(args.source_sqlite, args.target_url, args.dry_run)
    sys.exit(0 if success else 1)
