"""
Database Health Checks
======================
Sanitized connectivity and readiness verification for Supabase PostgreSQL and SQLite.
Zero credential leakage guaranteed.
"""

import time
from typing import Dict, Any, Optional
from sqlalchemy import text
from backend.config import get_config
from backend.db.engine import get_engine


def check_db_connectivity(database_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Verifies that the database engine can execute queries and measures roundtrip latency.
    """
    cfg = get_config()
    provider = getattr(cfg, "DATABASE_PROVIDER", "sqlite")
    start = time.perf_counter()
    status = {
        "provider": provider,
        "connected": False,
        "latency_ms": None,
        "error": None,
    }

    try:
        engine = get_engine(database_url)
        with engine.connect() as conn:
            val = conn.execute(text("SELECT 1;")).scalar()
            if val == 1:
                status["connected"] = True
                status["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
    except Exception as e:
        status["error"] = type(e).__name__

    return status


def get_database_metrics(database_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieves high-level schema metrics (total core tables and row summaries).
    """
    health = check_db_connectivity(database_url)
    if not health["connected"]:
        return {
            "health": health,
            "ready": False,
            "table_count": 0,
        }

    table_count = 0
    try:
        engine = get_engine(database_url)
        with engine.connect() as conn:
            if health["provider"] in ("supabase", "postgresql"):
                res = conn.execute(text("""
                    SELECT COUNT(*) 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public';
                """)).scalar()
                table_count = res or 0
            else:
                res = conn.execute(text("""
                    SELECT COUNT(*) 
                    FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%';
                """)).scalar()
                table_count = res or 0
    except Exception:
        pass

    return {
        "health": health,
        "ready": table_count >= 20,
        "table_count": table_count,
    }
