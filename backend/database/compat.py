"""
Database Compatibility Layer
============================
Preserves legacy SQLite helpers and initialization functions.
"""

import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional, Generator
from backend.config import get_config
from backend.logging_config import setup_logging

logger = setup_logging()

LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
    id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('minor','moderate','severe')),
    est_depth_cm REAL,
    confidence REAL,
    image_ref TEXT,
    timestamp REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'reported' CHECK(status IN ('reported','acknowledged','scheduled','repaired')),
    report_count INTEGER NOT NULL DEFAULT 1,
    address TEXT
);

CREATE INDEX IF NOT EXISTS idx_detections_location ON detections(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_detections_status ON detections(status);
CREATE INDEX IF NOT EXISTS idx_detections_status_sev ON detections(status, severity);
CREATE INDEX IF NOT EXISTS idx_detections_ts ON detections(timestamp);
"""

CIVICLENS_DOMAIN_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    address TEXT,
    severity TEXT NOT NULL DEFAULT 'minor' CHECK(severity IN ('minor','moderate','severe')),
    est_depth_cm REAL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'reported' CHECK(status IN ('reported','acknowledged','scheduled','in_progress','repaired','verified')),
    report_count INTEGER NOT NULL DEFAULT 1,
    first_reported_at REAL NOT NULL,
    last_reported_at REAL NOT NULL,
    resolved_at REAL
);

CREATE INDEX IF NOT EXISTS idx_incidents_coords ON incidents(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);

CREATE TABLE IF NOT EXISTS citizen_reports (
    id TEXT PRIMARY KEY,
    incident_id TEXT,
    source_type TEXT NOT NULL DEFAULT 'citizen_mobile',
    citizen_id TEXT,
    vehicle_id TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    description TEXT,
    language_code TEXT NOT NULL DEFAULT 'en',
    created_at REAL NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_incident ON citizen_reports(incident_id);

CREATE TABLE IF NOT EXISTS evidence_assets (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    file_path TEXT,
    sha256_hash TEXT,
    phash_value TEXT,
    mime_type TEXT,
    file_size_bytes INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    FOREIGN KEY(report_id) REFERENCES citizen_reports(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_evidence_sha256 ON evidence_assets(sha256_hash);

CREATE TABLE IF NOT EXISTS detections_v2 (
    id TEXT PRIMARY KEY,
    evidence_asset_id TEXT NOT NULL,
    defect_type TEXT NOT NULL DEFAULT 'pothole',
    bbox_x INTEGER DEFAULT 0,
    bbox_y INTEGER DEFAULT 0,
    bbox_w INTEGER DEFAULT 0,
    bbox_h INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.0,
    est_depth_cm REAL DEFAULT 0.0,
    severity TEXT NOT NULL DEFAULT 'minor',
    model_version TEXT DEFAULT 'yolov8-baseline',
    created_at REAL NOT NULL,
    FOREIGN KEY(evidence_asset_id) REFERENCES evidence_assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_decisions (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    candidate_incident_id TEXT,
    verdict TEXT NOT NULL,
    confidence_score REAL DEFAULT 0.0,
    spatial_distance_m REAL DEFAULT 0.0,
    visual_similarity REAL DEFAULT 0.0,
    reason TEXT,
    evaluated_at REAL NOT NULL,
    FOREIGN KEY(report_id) REFERENCES citizen_reports(id) ON DELETE CASCADE,
    FOREIGN KEY(candidate_incident_id) REFERENCES incidents(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS incident_observations (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    report_id TEXT NOT NULL,
    evidence_asset_id TEXT,
    detection_id TEXT,
    observed_at REAL NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES incidents(id) ON DELETE CASCADE,
    FOREIGN KEY(report_id) REFERENCES citizen_reports(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor_id TEXT,
    details TEXT,
    created_at REAL NOT NULL
);
"""


class PostgresCompatCursor:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=None):
        pg_sql = sql.replace("?", "%s")
        return self._cur.execute(pg_sql, params or ())

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        rows = self._cur.fetchall()
        return [dict(r) for r in rows]

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description


class PostgresCompatConnection:
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        try:
            import psycopg2.extras
            return PostgresCompatCursor(self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor))
        except ImportError:
            return PostgresCompatCursor(self._conn.cursor())

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


@contextmanager
def get_db(db_path: Optional[str] = None):
    """Context manager providing a database connection with dict/row access."""
    cfg = get_config()
    if db_path is None and getattr(cfg, "DATABASE_PROVIDER", "sqlite") in ("supabase", "postgresql"):
        from backend.db.engine import get_engine
        engine = get_engine(cfg.DATABASE_URL)
        raw_conn = engine.raw_connection()
        compat_conn = PostgresCompatConnection(raw_conn)
        try:
            yield compat_conn
            compat_conn.commit()
        except Exception:
            compat_conn.rollback()
            raise
        finally:
            compat_conn.close()
    else:
        path = db_path or cfg.DATABASE_PATH
        is_uri = path.startswith("file:")
        conn = sqlite3.connect(path, timeout=10.0, uri=is_uri)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes both legacy schema and CivicLens domain companion tables."""
    with get_db(db_path=db_path) as conn:
        conn.executescript(LEGACY_SCHEMA)
        conn.executescript(CIVICLENS_DOMAIN_SCHEMA)
    logger.info(f"Database schema initialized successfully at '{db_path or get_config().DATABASE_PATH}'")
