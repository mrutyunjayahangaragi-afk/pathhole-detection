"""
CivicLens Services Package
"""

from backend.services.location_service import LocationService, haversine_distance_m
from backend.services.duplicate_matching_service import DuplicateMatchingService
from backend.services.incident_service import IncidentService
from backend.services.report_service import ReportService
from backend.services.evidence_service import EvidenceService
from backend.services.detection_service import DetectionService

from backend.services.incident_state_machine_service import IncidentStateMachineService, IncidentStatus
from backend.services.department_management_service import DepartmentManagementService
from backend.services.incident_assignment_service import IncidentAssignmentService
from backend.services.inspection_resolution_service import InspectionResolutionService
from backend.services.municipal_dashboard_service import MunicipalDashboardService
from backend.services.municipal_communication_service import MunicipalCommunicationService

__all__ = [
    "LocationService",
    "haversine_distance_m",
    "DuplicateMatchingService",
    "IncidentService",
    "ReportService",
    "EvidenceService",
    "DetectionService",
    "IncidentStateMachineService",
    "IncidentStatus",
    "DepartmentManagementService",
    "IncidentAssignmentService",
    "InspectionResolutionService",
    "MunicipalDashboardService",
    "MunicipalCommunicationService",
]
