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

from backend.services.public_incident_service import PublicIncidentService
from backend.services.incident_follow_service import IncidentFollowService
from backend.services.notification_preference_service import NotificationPreferenceService
from backend.services.notification_outbox_service import NotificationOutboxService
from backend.services.notification_delivery_service import NotificationDeliveryService
from backend.services.in_app_notification_service import InAppNotificationService
from backend.services.public_transparency_service import PublicTransparencyService

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
    "PublicIncidentService",
    "IncidentFollowService",
    "NotificationPreferenceService",
    "NotificationOutboxService",
    "NotificationDeliveryService",
    "InAppNotificationService",
    "PublicTransparencyService",
]
