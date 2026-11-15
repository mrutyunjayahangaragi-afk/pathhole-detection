"""
AI Defect Detection API Routes
==============================
Provides endpoints for executing defect detection, tracking inference runs,
retrieving multi-object detections, and submitting human review feedback.
Strict anti-IDOR authorization guarantees citizens only access their own evidence.
"""

from flask import Blueprint, request, jsonify, g
from backend.auth import login_required
from backend.errors import ValidationError, NotFoundError, ForbiddenError
from backend.services.defect_detection_service import DefectDetectionService
from backend.services.detection_review_service import DetectionReviewService
from backend.services.detection_repository import DetectionRepository

detection_bp = Blueprint("detection_bp", __name__, url_prefix="/api/v1")

detection_service = DefectDetectionService()
review_service = DetectionReviewService()
repository = DetectionRepository()


def _is_staff() -> bool:
    """Helper returning True if current user is municipal officer or administrator."""
    return getattr(g.current_user, "role", "") in (
        "municipal_officer", "dept_admin", "system_admin"
    )


@detection_bp.route("/evidence/<asset_id>/detect", methods=["POST"])
@login_required
def trigger_detection(asset_id: str):
    """
    Triggers AI defect detection on the specified evidence image asset.
    Strictly restricted to the uploading citizen or municipal officers.
    """
    conf_threshold = None
    data = request.get_json(silent=True) or {}
    if "confidence_threshold" in data:
        try:
            val = float(data["confidence_threshold"])
            if not (0.0 <= val <= 1.0):
                raise ValidationError("confidence_threshold must be between 0.0 and 1.0")
            conf_threshold = val
        except ValueError:
            raise ValidationError("confidence_threshold must be a valid float")

    result = detection_service.process_evidence(
        evidence_asset_id=asset_id,
        requesting_user_id=g.current_user.id,
        is_officer_or_admin=_is_staff(),
        conf_threshold=conf_threshold,
    )

    status_code = 200 if result.get("status") == "success" else 422
    if result.get("error_code") == "MODEL_WEIGHTS_MISSING":
        status_code = 200  # Return 200 with clear diagnostics when weights are not configured

    return jsonify({
        "status": result.get("status", "success"),
        **result,
    }), status_code


@detection_bp.route("/evidence/<asset_id>/detections", methods=["GET"])
@login_required
def get_evidence_detections(asset_id: str):
    """Retrieves all defect detections and latest run for an authorized evidence asset."""
    result = detection_service.get_evidence_detections(
        evidence_asset_id=asset_id,
        requesting_user_id=g.current_user.id,
        is_officer_or_admin=_is_staff(),
    )
    return jsonify({
        "status": "success",
        **result,
    }), 200


@detection_bp.route("/reports/<report_id>/detections", methods=["GET"])
@login_required
def get_report_detections(report_id: str):
    """Retrieves detections across all evidence assets linked to a citizen report."""
    result = detection_service.get_report_detections(
        report_id=report_id,
        requesting_user_id=g.current_user.id,
        is_officer_or_admin=_is_staff(),
    )
    return jsonify({
        "status": "success",
        **result,
    }), 200


@detection_bp.route("/detection-runs/<run_id>", methods=["GET"])
@login_required
def get_detection_run(run_id: str):
    """Checks processing status and metadata of a specific detection run."""
    run = repository.get_run(run_id)
    if not run:
        raise NotFoundError(f"Detection run '{run_id}' not found")

    # Anti-IDOR check on the evidence asset
    detection_service.verify_evidence_access(
        evidence_asset_id=run["evidence_asset_id"],
        requesting_user_id=g.current_user.id,
        is_officer_or_admin=_is_staff(),
    )

    detections = repository.get_detections_for_run(run_id)
    return jsonify({
        "status": "success",
        "run": run,
        "defect_count": len(detections),
        "detections": detections,
    }), 200


@detection_bp.route("/detections/<detection_id>", methods=["GET"])
@login_required
def get_detection_detail(detection_id: str):
    """Fetches details for an individual defect detection."""
    det = repository.get_detection(detection_id)
    if not det:
        raise NotFoundError("Detection not found or access denied")

    evidence_id = det.get("evidence_asset_id")
    if evidence_id:
        detection_service.verify_evidence_access(
            evidence_asset_id=evidence_id,
            requesting_user_id=g.current_user.id,
            is_officer_or_admin=_is_staff(),
        )

    return jsonify({
        "status": "success",
        "detection": det,
    }), 200


@detection_bp.route("/detections/<detection_id>/review", methods=["POST"])
@login_required
def review_detection(detection_id: str):
    """
    Submits human review feedback on a defect detection.
    Permitted review statuses: 'confirmed', 'rejected', 'corrected', 'uncertain'.
    Citizens cannot alter model confidence, model version, or official verification status.
    """
    data = request.get_json(silent=True) or {}
    review_status = data.get("review_status")
    if not review_status:
        raise ValidationError("Field 'review_status' is required ('confirmed', 'rejected', 'corrected')")

    review_notes = data.get("review_notes") or data.get("notes")

    updated = review_service.submit_review(
        detection_id=detection_id,
        review_status=review_status,
        requesting_user_id=g.current_user.id,
        is_officer_or_admin=_is_staff(),
        review_notes=review_notes,
    )

    return jsonify({
        "status": "success",
        "message": f"Detection review updated to '{updated['review_status']}'",
        "detection": updated,
    }), 200


@detection_bp.route("/evidence/<asset_id>/reprocess", methods=["POST"])
@login_required
def reprocess_evidence(asset_id: str):
    """
    Reprocesses an evidence asset with the currently configured model version.
    Preserves historical detection runs.
    """
    data = request.get_json(silent=True) or {}
    conf_threshold = None
    if "confidence_threshold" in data:
        try:
            val = float(data["confidence_threshold"])
            if not (0.0 <= val <= 1.0):
                raise ValidationError("confidence_threshold must be between 0.0 and 1.0")
            conf_threshold = val
        except ValueError:
            raise ValidationError("confidence_threshold must be a valid float")

    result = detection_service.process_evidence(
        evidence_asset_id=asset_id,
        requesting_user_id=g.current_user.id,
        is_officer_or_admin=_is_staff(),
        conf_threshold=conf_threshold,
    )

    return jsonify({
        "status": result.get("status", "success"),
        **result,
    }), 200
