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

# Enforce isolated SQLite testing for unit tests
os.environ["DATABASE_PROVIDER"] = "sqlite"
os.environ["TESTING"] = "true"

from backend.config import TestingConfig
from backend.database import init_db
from backend.app import create_app


@pytest.fixture(scope="session")
def test_db_path():
    """Creates a temporary SQLite database file for testing in /tmp."""
    fd, path = tempfile.mkstemp(prefix="civiclens_test_", suffix=".db", dir="/tmp")
    os.close(fd)
    os.environ["TEST_DATABASE_PATH"] = path
    yield path
    if os.path.exists(path):
        os.remove(path)
    os.environ.pop("TEST_DATABASE_PATH", None)


@pytest.fixture
def test_config(test_db_path):
    """Returns a TestingConfig instance bound to the isolated test database."""
    os.environ["TEST_DATABASE_PATH"] = test_db_path
    config = TestingConfig()
    config.DATABASE_PATH = test_db_path
    config.DATABASE_URL = f"sqlite:///{test_db_path}"
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
    from backend.db.engine import reset_engine
    reset_engine()
    from backend.database import get_db
    with get_db(test_db_path) as conn:
        for tbl in [
            "official_invitations",
            "telemetry_events",
            "telemetry_devices",
            "report_evidence_v2",
            "report_items_v2",
            "citizen_reports_v2",
            "users",
            "detections",
            "citizen_reports",
            "incidents",
            "evidence_assets",
            "detections_v2",
            "match_decisions",
            "incident_observations",
            "audit_logs",
        ]:
            try:
                conn.execute(f"DELETE FROM {tbl}")
            except Exception:
                pass
    yield test_db_path
    reset_engine()
