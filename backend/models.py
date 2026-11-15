"""
Database layer for the pothole reporting backend.

Preserves full backward compatibility with original Roadstate functions:
- init_db()
- get_db()
- haversine_m()
- find_nearby_detection()
- insert_or_merge_detection()
"""

import sys
from pathlib import Path
_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Optional

from backend.config import get_config
from backend.database import get_db as db_get_db, init_db as db_init_db, LEGACY_SCHEMA
from backend.services.location_service import haversine_distance_m

# Dynamically resolve DB_PATH through centralized configuration
DB_PATH = get_config().DATABASE_PATH
SCHEMA = LEGACY_SCHEMA
DEDUP_RADIUS_M = get_config().DEDUP_RADIUS_METERS


def get_db():
    """Provides a SQLite database connection with row factory and foreign keys."""
    return db_get_db(DB_PATH)


def init_db():
    """Initializes the database schema."""
    db_init_db(DB_PATH)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in meters."""
    return haversine_distance_m(lat1, lon1, lat2, lon2)


def find_nearby_detection(conn: sqlite3.Connection, lat: float, lon: float) -> Optional[sqlite3.Row]:
    """
    Find an existing open (not yet repaired) detection within DEDUP_RADIUS_M
    of the given coordinates.
    """
    rows = conn.execute(
        "SELECT * FROM detections WHERE status != 'repaired'"
    ).fetchall()
    for row in rows:
        if haversine_m(lat, lon, row["latitude"], row["longitude"]) <= DEDUP_RADIUS_M:
            return row
    return None


def insert_or_merge_detection(
    vehicle_id: str,
    lat: float,
    lon: float,
    severity: str,
    est_depth_cm: float,
    confidence: float,
    image_ref: Optional[str],
    address: Optional[str] = None,
) -> dict:
    """
    Insert a new pothole report, or — if a matching report already exists
    nearby — merge into it (bump the report_count and refresh severity to
    the worse of the two estimates).
    """
    severity_rank = {"minor": 0, "moderate": 1, "severe": 2}
    now = time.time()

    with get_db() as conn:
        existing = find_nearby_detection(conn, lat, lon)
        if existing:
            merged_severity = (
                severity
                if severity_rank[severity] > severity_rank[existing["severity"]]
                else existing["severity"]
            )
            conn.execute(
                """UPDATE detections
                   SET report_count = report_count + 1,
                       severity = ?,
                       est_depth_cm = MAX(est_depth_cm, ?),
                       timestamp = ?
                   WHERE id = ?""",
                (merged_severity, est_depth_cm, now, existing["id"]),
            )
            row = conn.execute(
                "SELECT * FROM detections WHERE id = ?", (existing["id"],)
            ).fetchone()
            return {"merged": True, "detection": dict(row)}

        new_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO detections
               (id, vehicle_id, latitude, longitude, severity, est_depth_cm,
                confidence, image_ref, timestamp, status, report_count, address)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'reported', 1, ?)""",
            (new_id, vehicle_id, lat, lon, severity, est_depth_cm, confidence, image_ref, now, address),
        )
        row = conn.execute("SELECT * FROM detections WHERE id = ?", (new_id,)).fetchone()
        return {"merged": False, "detection": dict(row)}
