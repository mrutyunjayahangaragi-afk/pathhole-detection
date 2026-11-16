"""
Database Connection Management
==============================
Provides centralized database engine initialization, connection pooling,
and connection health checks for PostgreSQL (Supabase) and SQLite.
"""

from typing import Optional, Dict, Any
from sqlalchemy import text
from backend.config import get_config
from backend.db.engine import get_engine


def get_database_engine(url: Optional[str] = None):
    """Retrieves or creates the centralized SQLAlchemy engine."""
    return get_engine(url)


def check_database_health() -> Dict[str, Any]:
    """
    Checks active database connectivity and returns a status dictionary.
    Safe against credentials leakage.
    """
    engine = get_database_engine()
    cfg = get_config()
    status = {
        "provider": cfg.DATABASE_PROVIDER,
        "connected": False,
        "error": None,
    }
    try:
        with engine.connect() as conn:
            val = conn.execute(text("SELECT 1;")).scalar()
            if val == 1:
                status["connected"] = True
    except Exception as e:
        status["error"] = str(e)
    return status
