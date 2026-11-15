"""
CivicLens Domain Models & Value Objects
=======================================

Defines the core entities and value objects of the CivicLens domain model:
- Incident: One physical infrastructure defect in the real world.
- CitizenReport: An individual citizen's grievance submission.
- EvidenceAsset: An uploaded photograph or media file supporting a report.
- Detection: An AI defect detected within an evidence media asset.
- IncidentObservation: The association linking a report/evidence to an incident.
- MatchDecision: The audit record of comparing a report against candidate incidents.

These models strictly adhere to the domain rules:
1. One physical infrastructure issue = One canonical Incident.
2. An Incident is NOT a single report; it aggregates multiple reports.
3. An EvidenceAsset belongs to a report, not directly to an incident.
4. A Detection belongs to an EvidenceAsset.
5. An uncertain MatchDecision does NOT trigger automated merging.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
import time
import uuid


class SeverityLevel(str, Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"

    @classmethod
    def from_str(cls, val: str) -> "SeverityLevel":
        try:
            return cls(val.lower())
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid severity: '{val}'. Must be minor, moderate, or severe.")

    @property
    def rank(self) -> int:
        return {"minor": 0, "moderate": 1, "severe": 2}[self.value]

    def worse_of(self, other: "SeverityLevel") -> "SeverityLevel":
        return self if self.rank >= other.rank else other


class IncidentStatus(str, Enum):
    REPORTED = "reported"
    ACKNOWLEDGED = "acknowledged"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    REPAIRED = "repaired"
    VERIFIED = "verified"

    @classmethod
    def from_str(cls, val: str) -> "IncidentStatus":
        try:
            return cls(val.lower())
        except (ValueError, AttributeError):
            raise ValueError(
                f"Invalid status: '{val}'. Must be reported, acknowledged, scheduled, in_progress, repaired, or verified."
            )


class SourceType(str, Enum):
    CITIZEN_MOBILE = "citizen_mobile"
    CITIZEN_WEB = "citizen_web"
    VEHICLE_TELEMATICS = "vehicle_telematics"
    MANUAL_OFFICIAL = "manual_official"


class MatchVerdict(str, Enum):
    EXACT_DUPLICATE = "exact_duplicate"      # Auto-merged with high confidence
    PROBABLE_MATCH = "probable_match"        # Uncertain / flagged for human review
    DISTINCT_INCIDENT = "distinct_incident"  # New independent canonical incident


@dataclass
class EvidenceAsset:
    """Represents an uploaded media file (photo, video) providing evidence."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    report_id: Optional[str] = None
    file_path: Optional[str] = None
    sha256_hash: Optional[str] = None
    phash_value: Optional[str] = None
    mime_type: Optional[str] = None
    file_size_bytes: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "report_id": self.report_id,
            "file_path": self.file_path,
            "sha256_hash": self.sha256_hash,
            "phash_value": self.phash_value,
            "mime_type": self.mime_type,
            "file_size_bytes": self.file_size_bytes,
            "created_at": self.created_at,
        }


@dataclass
class Detection:
    """Represents an AI defect detected within an evidence media asset."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    evidence_asset_id: Optional[str] = None
    defect_type: str = "pothole"
    bbox_x: int = 0
    bbox_y: int = 0
    bbox_w: int = 0
    bbox_h: int = 0
    normalized_xmin: Optional[float] = None
    normalized_ymin: Optional[float] = None
    normalized_xmax: Optional[float] = None
    normalized_ymax: Optional[float] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    confidence: float = 0.0
    confidence_tier: str = "medium"
    est_depth_cm: float = 0.0
    severity: SeverityLevel = SeverityLevel.MINOR
    model_version: str = "yolov8-baseline"
    review_status: str = "unreviewed"
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[float] = None
    review_notes: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "evidence_asset_id": self.evidence_asset_id,
            "defect_type": self.defect_type,
            "bbox": [self.bbox_x, self.bbox_y, self.bbox_w, self.bbox_h],
            "normalized_bbox": {
                "xmin": self.normalized_xmin,
                "ymin": self.normalized_ymin,
                "xmax": self.normalized_xmax,
                "ymax": self.normalized_ymax,
            } if self.normalized_xmin is not None else None,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "confidence": self.confidence,
            "confidence_tier": self.confidence_tier,
            "est_depth_cm": self.est_depth_cm,
            "severity": self.severity.value,
            "model_version": self.model_version,
            "review_status": self.review_status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "review_notes": self.review_notes,
            "created_at": self.created_at,
        }


@dataclass
class CitizenReport:
    """An individual citizen or vehicle's submission about an infrastructure defect."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: Optional[str] = None  # May be None if match is uncertain
    source_type: SourceType = SourceType.CITIZEN_MOBILE
    citizen_id: Optional[str] = None
    vehicle_id: Optional[str] = None
    latitude: float = 0.0
    longitude: float = 0.0
    description: Optional[str] = None
    language_code: str = "en"  # "en" or "kn"
    evidence_assets: List[EvidenceAsset] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "source_type": self.source_type.value,
            "citizen_id": self.citizen_id,
            "vehicle_id": self.vehicle_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "description": self.description,
            "language_code": self.language_code,
            "evidence_count": len(self.evidence_assets),
            "created_at": self.created_at,
        }


@dataclass
class MatchDecision:
    """Audit record capturing the evaluation of a report against an incident."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    report_id: str = ""
    candidate_incident_id: Optional[str] = None
    verdict: MatchVerdict = MatchVerdict.DISTINCT_INCIDENT
    confidence_score: float = 0.0
    spatial_distance_m: float = 0.0
    visual_similarity: float = 0.0
    reason: str = ""
    evaluated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "report_id": self.report_id,
            "candidate_incident_id": self.candidate_incident_id,
            "verdict": self.verdict.value,
            "confidence_score": self.confidence_score,
            "spatial_distance_m": self.spatial_distance_m,
            "visual_similarity": self.visual_similarity,
            "reason": self.reason,
            "evaluated_at": self.evaluated_at,
        }


@dataclass
class IncidentObservation:
    """Associates a report and its evidence with a canonical incident."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    incident_id: str = ""
    report_id: str = ""
    evidence_asset_id: Optional[str] = None
    detection_id: Optional[str] = None
    observed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "report_id": self.report_id,
            "evidence_asset_id": self.evidence_asset_id,
            "detection_id": self.detection_id,
            "observed_at": self.observed_at,
        }


@dataclass
class Incident:
    """One physical infrastructure problem in the real world (The Canonical Incident)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    latitude: float = 0.0
    longitude: float = 0.0
    address: Optional[str] = None
    severity: SeverityLevel = SeverityLevel.MINOR
    est_depth_cm: float = 0.0
    status: IncidentStatus = IncidentStatus.REPORTED
    report_count: int = 1
    first_reported_at: float = field(default_factory=time.time)
    last_reported_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    
    # Navigation references (in-memory or hydrated via repositories)
    reports: List[CitizenReport] = field(default_factory=list)
    observations: List[IncidentObservation] = field(default_factory=list)

    def record_additional_report(
        self, report: CitizenReport, new_depth_cm: float = 0.0, new_severity: Optional[SeverityLevel] = None
    ) -> None:
        """
        Safely records an additional report into this canonical incident,
        incrementing the report count, updating the latest timestamp, and
        adjusting severity to the worse of the estimates.
        """
        self.report_count += 1
        self.last_reported_at = time.time()
        if new_depth_cm > self.est_depth_cm:
            self.est_depth_cm = new_depth_cm
        if new_severity is not None:
            self.severity = self.severity.worse_of(new_severity)
        self.reports.append(report)
        report.incident_id = self.id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address": self.address,
            "severity": self.severity.value,
            "est_depth_cm": self.est_depth_cm,
            "status": self.status.value,
            "report_count": self.report_count,
            "first_reported_at": self.first_reported_at,
            "last_reported_at": self.last_reported_at,
            "resolved_at": self.resolved_at,
        }
