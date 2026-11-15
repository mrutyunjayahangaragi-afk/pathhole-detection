"""
Database Engine Factory
=======================
Supports dual-engine operation:
- PostgreSQL + PostGIS when DATABASE_URL is set
- SQLite fallback for zero-dependency local development
"""

import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from typing import Optional

_engine = None
_SessionFactory = None


def _create_engine_for_url(url: str):
    if url.startswith("postgresql"):
        return create_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
    else:
        eng = create_engine(url, echo=False)

        @event.listens_for(eng, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return eng


def get_engine(database_url: Optional[str] = None):
    """Creates or returns the singleton SQLAlchemy engine."""
    global _engine
    if database_url is not None:
        if _engine is not None and str(_engine.url) == database_url:
            return _engine
        eng = _create_engine_for_url(database_url)
        if _engine is None:
            _engine = eng
        return eng

    if _engine is not None:
        return _engine

    url = os.environ.get("DATABASE_URL")
    if url:
        _engine = _create_engine_for_url(url)
    else:
        from backend.config import get_config
        cfg = get_config()
        sqlite_url = f"sqlite:///{cfg.DATABASE_PATH}"
        _engine = _create_engine_for_url(sqlite_url)

    return _engine


def get_session_factory(database_url: Optional[str] = None) -> sessionmaker:
    """Returns a session factory bound to the engine."""
    global _SessionFactory
    if database_url is None and _SessionFactory is not None:
        return _SessionFactory
    engine = get_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    if database_url is None:
        _SessionFactory = factory
    return factory


def get_scoped_session(database_url: Optional[str] = None) -> scoped_session:
    """Returns a thread-safe scoped session."""
    factory = get_session_factory(database_url)
    return scoped_session(factory)


def reset_engine():
    """Resets the engine singleton — used in testing."""
    global _engine, _SessionFactory
    if _engine:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
