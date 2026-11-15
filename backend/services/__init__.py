"""
CivicLens Services Package
"""

from backend.services.location_service import LocationService, haversine_distance_m
from backend.services.duplicate_matching_service import DuplicateMatchingService
from backend.services.incident_service import IncidentService
from backend.services.report_service import ReportService
from backend.services.evidence_service import EvidenceService
from backend.services.detection_service import DetectionService

__all__ = [
    "LocationService",
    "haversine_distance_m",
    "DuplicateMatchingService",
    "IncidentService",
    "ReportService",
    "EvidenceService",
    "DetectionService",
]
