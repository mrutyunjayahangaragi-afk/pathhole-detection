"""
Schema Initialization
=====================
Creates all CivicLens v2 tables using SQLAlchemy metadata.
Safe to call multiple times (checkfirst=True by default).
"""

from sqlalchemy import text
from backend.db.engine import get_engine
from backend.db.models import Base


def create_all_tables(database_url=None):
    """Creates all ORM-defined tables and performance composite indexes."""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine, checkfirst=True)
    try:
        with engine.begin() as conn:
            # Ensure auth_user_id exists on users
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN auth_user_id VARCHAR(64);"))
            except Exception:
                pass

            # Ensure municipality_id exists on departments
            try:
                conn.execute(text("ALTER TABLE departments ADD COLUMN municipality_id VARCHAR(36) REFERENCES municipalities(id);"))
            except Exception:
                pass

            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_incidents_status_cat ON incidents_v2(status, category);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_incidents_sev_pri ON incidents_v2(severity, priority);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reports_cit_created ON citizen_reports_v2(citizen_id, created_at);"))
    except Exception:
        pass
    return engine
