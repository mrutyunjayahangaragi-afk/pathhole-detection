"""
CivicLens Domain Rules and Invariants
======================================

Codifies the fundamental architectural and operational invariants of CivicLens:
1. One physical infrastructure issue = One canonical Incident.
2. Several citizen reports can and must refer to one Incident without creating duplicate incidents.
3. One report can contain multiple EvidenceAssets.
4. One media file can contain multiple defect Detections.
5. An uncertain match does NOT automatically merge incidents.
6. An individual report remains independently identifiable and retains its evidence.
"""

from typing import List, Tuple
from backend.domain.models import (
    Incident,
    CitizenReport,
    EvidenceAsset,
    Detection,
    MatchDecision,
    MatchVerdict,
)
from backend.errors import ValidationError


class CivicLensDomainRules:
    """Validator and enforcement engine for CivicLens core domain invariants."""

    @staticmethod
    def validate_report(report: CitizenReport) -> None:
        """Validates that a citizen report has acceptable coordinates and source."""
        if not (-90.0 <= report.latitude <= 90.0):
            raise ValidationError(f"Invalid latitude: {report.latitude}. Must be between -90 and 90.")
        if not (-180.0 <= report.longitude <= 180.0):
            raise ValidationError(f"Invalid longitude: {report.longitude}. Must be between -180 and 180.")
        if not (report.citizen_id or report.vehicle_id):
            raise ValidationError("A report must specify either citizen_id or vehicle_id.")

    @staticmethod
    def can_auto_merge(decision: MatchDecision) -> bool:
        """
        Rule: Only high-confidence EXACT_DUPLICATE verdicts may be automatically merged.
        PROBABLE_MATCH (uncertain) decisions MUST NOT be automatically merged.
        """
        return decision.verdict == MatchVerdict.EXACT_DUPLICATE and decision.confidence_score >= 0.85

    @staticmethod
    def assert_independent_report_identity(
        incident: Incident, reports: List[CitizenReport]
    ) -> bool:
        """
        Rule: Every report must retain its own unique identifier and timestamp
        even when associated with a single canonical incident.
        """
        report_ids = [r.id for r in reports]
        if len(report_ids) != len(set(report_ids)):
            return False  # Duplicated report IDs violate independent identity
        for r in reports:
            if r.incident_id != incident.id:
                return False
        return True

    @staticmethod
    def assert_multiple_evidence_per_report(report: CitizenReport, assets: List[EvidenceAsset]) -> bool:
        """
        Rule: One citizen report can hold zero, one, or multiple evidence assets.
        """
        return len(assets) >= 0 and all(a.report_id == report.id for a in assets)

    @staticmethod
    def assert_multiple_detections_per_media(
        asset: EvidenceAsset, detections: List[Detection]
    ) -> bool:
        """
        Rule: A single image or media asset can contain multiple defect detections.
        """
        return all(d.evidence_asset_id == asset.id for d in detections)
