"""
Pytest Fixtures for CivicLens / Roadstate Test Suite
====================================================

Sets up an isolated, temporary SQLite test database and Flask test client
for unit and integration tests. Guarantees production and demo databases
are never touched during test execution.
"""

import os
import tempfile
import pytest
from flask import Flask

from backend.config import TestingConfig
from backend.database import init_db
from backend.app import create_app


@pytest.fixture(scope="session")
def test_db_path():
    """Creates a temporary SQLite database file for testing."""
    fd, path = tempfile.mkstemp(prefix="civiclens_test_", suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def test_config(test_db_path):
    """Returns a TestingConfig instance bound to the isolated test database."""
    config = TestingConfig()
    config.DATABASE_PATH = test_db_path
    config.NOMINATIM_RATE_LIMIT_SECONDS = 0.0
    return config


@pytest.fixture
def app(test_config, test_db_path):
    """Initializes and returns a Flask application using the test configuration."""
    init_db(test_db_path)
    application = create_app(test_config)
    return application


@pytest.fixture
def client(app):
    """Returns a Flask test client for issuing test requests."""
    return app.test_client()


@pytest.fixture
def clean_db(test_db_path):
    """Cleans all test tables before each test that requires an empty state."""
    init_db(test_db_path)
    from backend.database import get_db
    with get_db(test_db_path) as conn:
        conn.execute("DELETE FROM detections")
        conn.execute("DELETE FROM citizen_reports")
        conn.execute("DELETE FROM incidents")
        conn.execute("DELETE FROM evidence_assets")
        conn.execute("DELETE FROM detections_v2")
        conn.execute("DELETE FROM match_decisions")
        conn.execute("DELETE FROM incident_observations")
        conn.execute("DELETE FROM audit_logs")
    yield test_db_path
