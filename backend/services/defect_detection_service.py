"""
Defect Detection Service
========================
High-level orchestrator for AI-powered road and infrastructure defect detection:
1. Validates citizen authorization and retrieves evidence file
2. Validates image integrity and normalizes EXIF orientation
3. Preprocesses image for object detection model input
4. Executes model inference via configured ModelProvider
5. Post-processes predictions: NMS deduplication, confidence tiering, normalized coords
6. Persists DetectionRun and individual Detection entities in PostgreSQL / SQLite
7. Records processing duration and audit metadata
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.db.engine import get_session_factory
from backend.db.models import EvidenceAsset, ReportEvidence, CitizenReport
from backend.errors import NotFoundError, ValidationError, ForbiddenError
from backend.services.image_validation_service import ImageValidationService
from backend.services.image_preprocessing_service import ImagePreprocessingService
from backend.services.model_provider import (
    BaseModelProvider, YoloModelProvider, ModelWeightsMissingError, ModelNotAvailableError
)
from backend.services.detection_postprocessing_service import DetectionPostprocessingService
from backend.services.detection_repository import DetectionRepository


class DefectDetectionService:
    """Orchestrates end-to-end defect detection inference and database persistence."""

    def __init__(
        self,
        model_provider: Optional[BaseModelProvider] = None,
        validation_service: Optional[ImageValidationService] = None,
        preprocessing_service: Optional[ImagePreprocessingService] = None,
        postprocessing_service: Optional[DetectionPostprocessingService] = None,
        repository: Optional[DetectionRepository] = None,
        session_factory=None,
    ):
        self._custom_session_factory = session_factory
        self.validation_service = validation_service or ImageValidationService()
        self.preprocessing_service = preprocessing_service or ImagePreprocessingService()
        self.postprocessing_service = postprocessing_service or DetectionPostprocessingService()
        self.repository = repository or DetectionRepository(session_factory=session_factory)
        self.model_provider = model_provider or self._build_default_model_provider()

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def _build_default_model_provider(self) -> BaseModelProvider:
        """Instantiates default YoloModelProvider reading from backend config."""
        from backend.config import get_config
        cfg = get_config()
        return YoloModelProvider(
            weights_path=getattr(cfg, "MODEL_WEIGHTS_PATH", "weights/pothole_yolov8.pt"),
            model_name=getattr(cfg, "MODEL_NAME", "yolov8-pothole"),
            model_version=getattr(cfg, "MODEL_VERSION", "v1.0.0"),
        )

    def verify_evidence_access(
        self,
        evidence_asset_id: str,
        requesting_user_id: str,
        is_officer_or_admin: bool = False,
    ) -> Path:
        """
        Verifies permission and returns absolute local Path to the evidence image.
        Raises NotFoundError if not authorized (anti-IDOR).
        """
        db = self._session_factory()
        try:
            asset = db.query(EvidenceAsset).filter_by(id=evidence_asset_id).first()
            if not asset or not asset.storage_key:
                raise NotFoundError("Evidence asset not found")

            if not is_officer_or_admin:
                link = (
                    db.query(ReportEvidence)
                    .join(CitizenReport, ReportEvidence.report_id == CitizenReport.id)
                    .filter(
                        ReportEvidence.evidence_asset_id == evidence_asset_id,
                        CitizenReport.citizen_id == requesting_user_id,
                    )
                    .first()
                )
                if not link:
                    raise NotFoundError("Evidence asset not found or access denied")

            p = Path(asset.storage_key)
            if not p.exists():
                raise NotFoundError("Evidence file missing from disk storage")
            return p
        finally:
            db.close()

    def process_evidence(
        self,
        evidence_asset_id: str,
        requesting_user_id: str,
        is_officer_or_admin: bool = False,
        conf_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Executes the full defect detection pipeline on an authorized evidence asset.
        """
        start_time = time.perf_counter()

        # 1. Verify access & retrieve image path
        image_path = self.verify_evidence_access(
            evidence_asset_id=evidence_asset_id,
            requesting_user_id=requesting_user_id,
            is_officer_or_admin=is_officer_or_admin,
        )

        # 2. Create DetectionRun record in DB
        run_id = self.repository.create_run(
            evidence_asset_id=evidence_asset_id,
            model_name=self.model_provider.model_name,
            model_version=self.model_provider.model_version,
        )

        try:
            # 3. Validate image and normalize EXIF orientation
            val_res = self.validation_service.validate_and_load(image_path)
            if not val_res.is_valid:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                self.repository.update_run_status(
                    run_id=run_id,
                    status="failed",
                    duration_ms=duration_ms,
                    error_code=val_res.error_code or "VALIDATION_FAILED",
                    error_message=val_res.error_message,
                )
                return {
                    "status": "failed",
                    "run_id": run_id,
                    "error_code": val_res.error_code,
                    "error_message": val_res.error_message,
                    "duration_ms": duration_ms,
                    "detections": [],
                }

            # 4. Check model availability
            if not self.model_provider.is_available():
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                err_msg = (
                    f"Model weights file not configured or not found. "
                    f"Place a trained YOLO .pt file at '{getattr(self.model_provider, 'weights_path', 'weights/')}' "
                    f"to enable live defect detection."
                )
                self.repository.update_run_status(
                    run_id=run_id,
                    status="failed",
                    duration_ms=duration_ms,
                    error_code="MODEL_WEIGHTS_MISSING",
                    error_message=err_msg,
                )
                return {
                    "status": "failed",
                    "run_id": run_id,
                    "error_code": "MODEL_WEIGHTS_MISSING",
                    "error_message": err_msg,
                    "duration_ms": duration_ms,
                    "detections": [],
                }

            # 5. Preprocess image
            preprocessed = self.preprocessing_service.preprocess(val_res.image)

            # 6. Run model inference
            eff_conf = conf_threshold if conf_threshold is not None else self.postprocessing_service.min_confidence
            raw_predictions = self.model_provider.predict(preprocessed.pil_image, conf_threshold=eff_conf)

            # Map raw boxes from preprocessed space back to original image space
            adjusted_predictions = []
            for p in raw_predictions:
                x, y, w, h = self.preprocessing_service.inverse_transform_box(p.box_xyxy, preprocessed)
                from backend.services.model_provider import RawPrediction
                adjusted_predictions.append(
                    RawPrediction(
                        class_name=p.class_name,
                        confidence=p.confidence,
                        box_xyxy=(float(x), float(y), float(x + w), float(y + h)),
                        est_depth_cm=p.est_depth_cm,
                    )
                )

            # 7. Post-process (NMS, normalization, confidence tiers, severity)
            processed_detections = self.postprocessing_service.postprocess(
                predictions=adjusted_predictions,
                image_width=val_res.width,
                image_height=val_res.height,
            )

            # 8. Save individual detections in DB
            self.repository.save_detections(
                run_id=run_id,
                evidence_asset_id=evidence_asset_id,
                detections=processed_detections,
                model_version=self.model_provider.model_version,
            )

            # 9. Determine final run status
            final_status = "completed"

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            self.repository.update_run_status(
                run_id=run_id,
                status=final_status,
                duration_ms=duration_ms,
            )

            # 10. Query serialized results
            detections_data = self.repository.get_detections_for_run(run_id)

            return {
                "status": "success",
                "run_id": run_id,
                "processing_status": final_status,
                "model_name": self.model_provider.model_name,
                "model_version": self.model_provider.model_version,
                "duration_ms": duration_ms,
                "defect_count": len(detections_data),
                "detections": detections_data,
                "image_width": val_res.width,
                "image_height": val_res.height,
            }

        except Exception as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            err_code = "INFERENCE_FAILED"
            if isinstance(e, (ModelWeightsMissingError, ModelNotAvailableError)):
                err_code = "MODEL_WEIGHTS_MISSING"
            self.repository.update_run_status(
                run_id=run_id,
                status="failed",
                duration_ms=duration_ms,
                error_code=err_code,
                error_message=str(e),
            )
            return {
                "status": "failed",
                "run_id": run_id,
                "error_code": err_code,
                "error_message": str(e),
                "duration_ms": duration_ms,
                "detections": [],
            }

    def get_evidence_detections(
        self,
        evidence_asset_id: str,
        requesting_user_id: str,
        is_officer_or_admin: bool = False,
    ) -> Dict[str, Any]:
        """
        Retrieves detection history and latest detections for an authorized evidence asset.
        """
        self.verify_evidence_access(
            evidence_asset_id=evidence_asset_id,
            requesting_user_id=requesting_user_id,
            is_officer_or_admin=is_officer_or_admin,
        )

        latest_run = self.repository.get_latest_run_for_evidence(evidence_asset_id)
        detections = self.repository.get_detections_for_evidence(evidence_asset_id)

        return {
            "evidence_asset_id": evidence_asset_id,
            "latest_run": latest_run,
            "defect_count": len(detections),
            "detections": detections,
        }

    def get_report_detections(
        self,
        report_id: str,
        requesting_user_id: str,
        is_officer_or_admin: bool = False,
    ) -> Dict[str, Any]:
        """
        Retrieves detections across all evidence assets associated with a citizen report.
        """
        db = self._session_factory()
        try:
            report = db.query(CitizenReport).filter_by(id=report_id).first()
            if not report:
                raise NotFoundError("Report not found or access denied")

            if not is_officer_or_admin and report.citizen_id != requesting_user_id:
                raise NotFoundError("Report not found or access denied")

            evidence_links = db.query(ReportEvidence).filter_by(report_id=report.id).all()
            all_assets_detections = []

            for link in evidence_links:
                asset_id = link.evidence_asset_id
                latest_run = self.repository.get_latest_run_for_evidence(asset_id)
                dets = self.repository.get_detections_for_evidence(asset_id)
                all_assets_detections.append({
                    "evidence_asset_id": asset_id,
                    "latest_run": latest_run,
                    "defect_count": len(dets),
                    "detections": dets,
                })

            total_defects = sum(item["defect_count"] for item in all_assets_detections)

            return {
                "report_id": report.id,
                "report_reference": report.report_reference,
                "evidence_count": len(evidence_links),
                "total_defects_detected": total_defects,
                "evidence_detections": all_assets_detections,
            }
        finally:
            db.close()
