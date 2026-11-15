"""
Database Engine Factory
=======================
Supports dual-engine operation:
- PostgreSQL + PostGIS when DATABASE_URL is set
- SQLite fallback for zero-dependency local development
"""

import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from typing import Optional, Dict

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None
_engines: Dict[str, Engine] = {}
_session_factories: Dict[str, sessionmaker] = {}


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
    global _engine, _engines
    if database_url is None:
        try:
            from flask import current_app
            if current_app:
                db_path = current_app.config.get("DATABASE_PATH")
                if db_path:
                    database_url = f"sqlite:///{db_path}"
        except (RuntimeError, ImportError):
            pass

    if database_url is None and _engine is not None:
        return _engine

    if database_url is None:
        url = os.environ.get("DATABASE_URL")
        if url:
            database_url = url
        else:
            from backend.config import get_config
            cfg = get_config()
            database_url = f"sqlite:///{cfg.DATABASE_PATH}"

    if database_url in _engines:
        return _engines[database_url]

    eng = _create_engine_for_url(database_url)
    _engines[database_url] = eng
    _engine = eng
    return eng


def get_session_factory(database_url: Optional[str] = None) -> sessionmaker:
    """Returns a session factory bound to the engine."""
    global _SessionFactory, _session_factories
    engine = get_engine(database_url)
    url_key = str(engine.url)
    if url_key in _session_factories:
        return _session_factories[url_key]
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    _session_factories[url_key] = factory
    _SessionFactory = factory
    return factory


def get_scoped_session(database_url: Optional[str] = None) -> scoped_session:
    """Returns a thread-safe scoped session."""
    factory = get_session_factory(database_url)
    return scoped_session(factory)


def reset_engine():
    """Resets the engine singleton — used in testing."""
    global _engine, _SessionFactory, _engines, _session_factories
    for eng in list(_engines.values()):
        try:
            eng.dispose()
        except Exception:
            pass
    _engines.clear()
    _session_factories.clear()
    _engine = None
    _SessionFactory = None
