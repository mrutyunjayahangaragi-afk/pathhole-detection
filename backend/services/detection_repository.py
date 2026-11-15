"""
Detection Repository
====================
Provides transactional database access for DetectionRun and Detection entities.
Supports SQLite and Supabase PostgreSQL through SQLAlchemy session management.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from backend.db.engine import get_session_factory
from backend.db.models import (
    DetectionRun, Detection, EvidenceAsset, ReportEvidence, CitizenReport, User
)
from backend.services.detection_postprocessing_service import ProcessedDetection
from backend.errors import NotFoundError


class DetectionRepository:
    """Manages database persistence for AI detection runs and individual defect detections."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session(self) -> Session:
        factory = self._custom_session_factory or get_session_factory()
        return factory()

    def create_run(
        self,
        evidence_asset_id: str,
        model_name: str,
        model_version: str,
    ) -> str:
        """Creates and persists an initial DetectionRun record in 'processing' status."""
        db = self._session
        try:
            run_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            run = DetectionRun(
                id=run_id,
                evidence_asset_id=evidence_asset_id,
                model_name=model_name,
                model_version=model_version,
                processing_status="running",
                started_at=now,
                created_at=now,
            )
            db.add(run)
            db.commit()
            return run_id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def update_run_status(
        self,
        run_id: str,
        status: str,
        duration_ms: Optional[float] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Updates the status and performance metrics of a DetectionRun."""
        db = self._session
        try:
            run = db.query(DetectionRun).filter_by(id=run_id).first()
            if not run:
                raise NotFoundError(f"DetectionRun '{run_id}' not found")

            run.processing_status = status
            run.completed_at = datetime.now(timezone.utc)
            if duration_ms is not None:
                run.processing_duration_ms = duration_ms
            if error_code is not None:
                run.error_code = error_code
            if error_message is not None:
                run.error_message = error_message

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def save_detections(
        self,
        run_id: str,
        evidence_asset_id: str,
        detections: List[ProcessedDetection],
        model_version: str,
    ) -> List[str]:
        """
        Persists all detected defects associated with a DetectionRun.
        Guarantees that multiple distinct defects remain separate rows.
        """
        db = self._session
        saved_ids: List[str] = []
        try:
            now = datetime.now(timezone.utc)
            for d in detections:
                det_id = str(uuid.uuid4())
                row = Detection(
                    id=det_id,
                    detection_run_id=run_id,
                    evidence_asset_id=evidence_asset_id,
                    detected_category=d.defect_category,
                    confidence_score=d.confidence,
                    confidence_tier=d.confidence_tier,
                    bbox_x=d.bbox_x,
                    bbox_y=d.bbox_y,
                    bbox_w=d.bbox_w,
                    bbox_h=d.bbox_h,
                    normalized_xmin=d.normalized_xmin,
                    normalized_ymin=d.normalized_ymin,
                    normalized_xmax=d.normalized_xmax,
                    normalized_ymax=d.normalized_ymax,
                    image_width=d.image_width,
                    image_height=d.image_height,
                    est_depth_cm=d.est_depth_cm,
                    severity=d.severity,
                    model_version=model_version,
                    review_status=d.review_status,
                    created_at=now,
                )
                db.add(row)
                saved_ids.append(det_id)

            db.commit()
            return saved_ids
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetches a single DetectionRun with execution metadata."""
        db = self._session
        try:
            run = db.query(DetectionRun).filter_by(id=run_id).first()
            if not run:
                return None
            return {
                "id": run.id,
                "evidence_asset_id": run.evidence_asset_id,
                "model_name": run.model_name,
                "model_version": run.model_version,
                "processing_status": run.processing_status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "processing_duration_ms": run.processing_duration_ms,
                "error_code": run.error_code,
                "error_message": run.error_message,
                "created_at": run.created_at.isoformat() if run.created_at else None,
            }
        finally:
            db.close()

    def get_detections_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        """Retrieves all defect detections generated by a specific run."""
        db = self._session
        try:
            rows = db.query(Detection).filter_by(detection_run_id=run_id).all()
            return [self._serialize_detection(r) for r in rows]
        finally:
            db.close()

    def get_detections_for_evidence(self, evidence_asset_id: str) -> List[Dict[str, Any]]:
        """Retrieves all detections linked to an evidence media asset."""
        db = self._session
        try:
            rows = db.query(Detection).filter_by(evidence_asset_id=evidence_asset_id).all()
            return [self._serialize_detection(r) for r in rows]
        finally:
            db.close()

    def get_latest_run_for_evidence(self, evidence_asset_id: str) -> Optional[Dict[str, Any]]:
        """Returns the most recent DetectionRun for a given evidence asset."""
        db = self._session
        try:
            run = (
                db.query(DetectionRun)
                .filter_by(evidence_asset_id=evidence_asset_id)
                .order_by(DetectionRun.created_at.desc())
                .first()
            )
            if not run:
                return None
            return {
                "id": run.id,
                "evidence_asset_id": run.evidence_asset_id,
                "model_name": run.model_name,
                "model_version": run.model_version,
                "processing_status": run.processing_status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "processing_duration_ms": run.processing_duration_ms,
                "error_code": run.error_code,
                "error_message": run.error_message,
                "created_at": run.created_at.isoformat() if run.created_at else None,
            }
        finally:
            db.close()

    def get_detection(self, detection_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single defect detection by ID."""
        db = self._session
        try:
            det = db.query(Detection).filter_by(id=detection_id).first()
            if not det:
                return None
            return self._serialize_detection(det)
        finally:
            db.close()

    def update_detection_review(
        self,
        detection_id: str,
        review_status: str,
        reviewed_by: Optional[str] = None,
        review_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates human review verdict on an individual detection."""
        db = self._session
        try:
            det = db.query(Detection).filter_by(id=detection_id).first()
            if not det:
                raise NotFoundError(f"Detection '{detection_id}' not found")

            det.review_status = review_status
            det.reviewed_by = reviewed_by
            det.reviewed_at = datetime.now(timezone.utc)
            if review_notes is not None:
                det.review_notes = review_notes

            db.commit()
            return self._serialize_detection(det)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _serialize_detection(self, r: Detection) -> Dict[str, Any]:
        """Serializes an ORM Detection entity into a clean dict."""
        return {
            "id": r.id,
            "detection_run_id": r.detection_run_id,
            "evidence_asset_id": r.evidence_asset_id,
            "category": r.detected_category,
            "detected_category": r.detected_category,
            "confidence": r.confidence_score,
            "confidence_tier": r.confidence_tier or "medium",
            "bbox_pixels": {
                "x": r.bbox_x,
                "y": r.bbox_y,
                "width": r.bbox_w,
                "height": r.bbox_h,
            },
            "normalized_bbox": {
                "xmin": r.normalized_xmin,
                "ymin": r.normalized_ymin,
                "xmax": r.normalized_xmax,
                "ymax": r.normalized_ymax,
            } if r.normalized_xmin is not None else None,
            "image_dimensions": {
                "width": r.image_width,
                "height": r.image_height,
            } if r.image_width else None,
            "est_depth_cm": r.est_depth_cm,
            "severity": r.severity,
            "model_version": r.model_version,
            "review_status": r.review_status,
            "reviewed_by": r.reviewed_by,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "review_notes": r.review_notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
