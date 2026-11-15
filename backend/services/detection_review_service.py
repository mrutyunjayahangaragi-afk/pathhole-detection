"""
Detection Review Service
========================
Manages human review of uncertain AI defect detections:
- Allows citizens to review AI suggestions on their own submitted reports
- Allows municipal officers to audit and confirm detections
- Prevents IDOR by verifying report ownership before permitting feedback
- Enforces domain boundaries: Citizen AI review does NOT alter official incident verification
"""

from typing import Any, Dict, Optional
from backend.db.engine import get_session_factory
from backend.db.models import (
    Detection, DetectionRun, EvidenceAsset, ReportEvidence, CitizenReport, User
)
from backend.services.detection_repository import DetectionRepository
from backend.errors import NotFoundError, ValidationError, ForbiddenError

VALID_REVIEW_STATUSES = {"confirmed", "rejected", "corrected", "uncertain"}


class DetectionReviewService:
    """Manages authorization and workflow for human feedback on AI detections."""

    def __init__(self, repository: Optional[DetectionRepository] = None, session_factory=None):
        self._custom_session_factory = session_factory
        self.repository = repository or DetectionRepository(session_factory=session_factory)

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def submit_review(
        self,
        detection_id: str,
        review_status: str,
        requesting_user_id: str,
        is_officer_or_admin: bool = False,
        review_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submits review verdict on a detection with strict authorization checking.
        """
        status_clean = review_status.strip().lower() if review_status else ""
        if status_clean not in VALID_REVIEW_STATUSES:
            raise ValidationError(
                f"Invalid review_status '{status_clean}'. Allowed: {sorted(VALID_REVIEW_STATUSES)}"
            )

        # 1. Authorization check
        db = self._session_factory()
        try:
            det = db.query(Detection).filter_by(id=detection_id).first()
            if not det:
                raise NotFoundError("Detection not found or access denied")

            evidence_id = det.evidence_asset_id
            if not evidence_id and det.detection_run_id:
                run = db.query(DetectionRun).filter_by(id=det.detection_run_id).first()
                if run:
                    evidence_id = run.evidence_asset_id

            if not is_officer_or_admin:
                # Citizen must own the report linked to this evidence
                link = (
                    db.query(ReportEvidence)
                    .join(CitizenReport, ReportEvidence.report_id == CitizenReport.id)
                    .filter(
                        ReportEvidence.evidence_asset_id == evidence_id,
                        CitizenReport.citizen_id == requesting_user_id,
                    )
                    .first()
                )
                if not link:
                    raise NotFoundError("Detection not found or access denied")

        finally:
            db.close()

        # 2. Update via repository
        return self.repository.update_detection_review(
            detection_id=detection_id,
            review_status=status_clean,
            reviewed_by=requesting_user_id,
            review_notes=review_notes.strip() if review_notes else None,
        )
