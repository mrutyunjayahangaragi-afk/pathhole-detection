"""
CivicLens Modular Database Package
==================================
Centralized database connection, session handling, and domain repositories.
"""

from backend.database.connection import get_database_engine, check_database_health
from backend.database.session import get_db_session, transactional_session
from backend.database.compat import init_db, get_db, LEGACY_SCHEMA, CIVICLENS_DOMAIN_SCHEMA
from backend.db.models import (
    User, Municipality, Department, DepartmentMembership, OfficialInvitation,
    Incident, CitizenReport, ReportItem, EvidenceAsset, AuditLog
)

__all__ = [
    "get_database_engine",
    "check_database_health",
    "get_db_session",
    "transactional_session",
    "init_db",
    "get_db",
    "LEGACY_SCHEMA",
    "CIVICLENS_DOMAIN_SCHEMA",
    "User",
    "Municipality",
    "Department",
    "DepartmentMembership",
    "OfficialInvitation",
    "Incident",
    "CitizenReport",
    "ReportItem",
    "EvidenceAsset",
    "AuditLog",
]
