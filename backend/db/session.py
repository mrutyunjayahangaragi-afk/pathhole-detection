"""
Database Session Helpers
========================
Provides transactional context managers for service-layer use.
"""

from contextlib import contextmanager
from backend.db.engine import get_session_factory


@contextmanager
def transactional_session(database_url=None):
    """Provides a transactional session scope — commits on success, rolls back on error."""
    session = get_session_factory(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
