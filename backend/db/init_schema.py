"""
Schema Initialization
=====================
Creates all CivicLens v2 tables using SQLAlchemy metadata.
Safe to call multiple times (checkfirst=True by default).
"""

from backend.db.engine import get_engine
from backend.db.models import Base


def create_all_tables(database_url=None):
    """Creates all ORM-defined tables if they do not exist."""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine, checkfirst=True)
    return engine
