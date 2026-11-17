"""
CivicLens Repositories Package
==============================
Domain repositories for clean data access and business logic isolation.
"""

from backend.database.repositories.profile_repository import ProfileRepository
from backend.database.repositories.organization_repository import OrganizationRepository
from backend.database.repositories.role_repository import RoleRepository
from backend.database.repositories.incident_repository import IncidentRepository
from backend.database.repositories.report_repository import ReportRepository
from backend.database.repositories.evidence_repository import EvidenceRepository
from backend.database.repositories.detection_repository import DetectionRepository
from backend.database.repositories.matching_repository import MatchingRepository
from backend.database.repositories.department_repository import DepartmentRepository
from backend.database.repositories.assignment_repository import AssignmentRepository
from backend.database.repositories.telemetry_repository import TelemetryRepository
from backend.database.repositories.notification_repository import NotificationRepository
from backend.database.repositories.audit_repository import AuditRepository

__all__ = [
    "ProfileRepository",
    "OrganizationRepository",
    "RoleRepository",
    "IncidentRepository",
    "ReportRepository",
    "EvidenceRepository",
    "DetectionRepository",
    "MatchingRepository",
    "DepartmentRepository",
    "AssignmentRepository",
    "TelemetryRepository",
    "NotificationRepository",
    "AuditRepository",
]
