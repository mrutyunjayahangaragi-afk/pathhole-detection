"""
Database Session Management
===========================
Provides scoped session factories and context managers with automatic rollback on error.
"""

from contextlib import contextmanager
from typing import Generator
from sqlalchemy.orm import Session
from backend.db.engine import get_session_factory


def get_db_session() -> Session:
    """Returns a new database session instance from the centralized factory."""
    SessionFactory = get_session_factory()
    return SessionFactory()


@contextmanager
def transactional_session() -> Generator[Session, None, None]:
    """
    Context manager that yields a transactional session,
    automatically committing on completion or rolling back on exception.
    """
    session = get_db_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
