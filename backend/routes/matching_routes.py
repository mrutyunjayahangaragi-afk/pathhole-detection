"""
Duplicate Incident Matching & Decision Routes
=============================================
Provides endpoints for evaluating report items for duplicate candidate incidents,
inspecting multi-signal match explanations, managing the municipal review queue,
confirming canonical incident links or new incidents, and consolidating incidents.

Authorization:
- Citizens can evaluate and inspect their own report items.
- Municipal matching queue and official decision actions strictly require
  staff roles ('municipal_officer', 'dept_admin', 'system_admin').
"""

from flask import Blueprint, request, jsonify, g
from backend.auth import login_required
from backend.errors import ValidationError, NotFoundError, ForbiddenError
from backend.services.duplicate_matching_service import DuplicateMatchingService
from backend.services.match_decision_service import MatchDecisionService
from backend.services.incident_consolidation_service import IncidentConsolidationService
from backend.db.engine import get_session_factory
from backend.db.models import ReportItem, MatchEvaluation

matching_bp = Blueprint("matching_bp", __name__, url_prefix="/api/v1/matching")

matching_service = DuplicateMatchingService()
decision_service = MatchDecisionService()
consolidation_service = IncidentConsolidationService()


def _is_staff() -> bool:
    """Helper returning True if current user is municipal officer or administrator."""
    return getattr(g.current_user, "role", "") in (
        "municipal_officer", "dept_admin", "system_admin"
    )


@matching_bp.route("/evaluate/<item_id>", methods=["POST"])
@login_required
def evaluate_report_item(item_id: str):
    """
    Triggers multi-signal candidate evaluation for a report item.
    Allowed for the report owner or municipal officers.
    """
    db = get_session_factory()()
    try:
        item = db.query(ReportItem).filter_by(id=item_id).first()
        if not item:
            raise NotFoundError(f"ReportItem '{item_id}' not found")

        # Anti-IDOR: Check ownership if not staff
        if not _is_staff() and item.report.citizen_id != g.current_user.id:
            raise ForbiddenError("You are not authorized to evaluate this report item.")
    finally:
        db.close()

    idempotency_key = request.headers.get("Idempotency-Key")
    result = matching_service.evaluate_report_item(
        report_item_id=item_id,
        idempotency_key=idempotency_key,
    )

    return jsonify({
        "status": "success",
        "data": result,
    }), 200


@matching_bp.route("/evaluations/<eval_id>", methods=["GET"])
@login_required
def get_evaluation(eval_id: str):
    """
    Retrieves full details of a match evaluation and its scored candidates.
    """
    db = get_session_factory()()
    try:
        eval_record = db.query(MatchEvaluation).filter_by(id=eval_id).first()
        if not eval_record:
            raise NotFoundError(f"MatchEvaluation '{eval_id}' not found")

        item = db.query(ReportItem).filter_by(id=eval_record.report_item_id).first()
        if not _is_staff() and (not item or item.report.citizen_id != g.current_user.id):
            raise ForbiddenError("You are not authorized to view this evaluation.")

        candidates = eval_record.candidates
        serialized = matching_service._serialize_evaluation(eval_record, candidates, db)

        return jsonify({
            "status": "success",
            "data": serialized,
        }), 200
    finally:
        db.close()


@matching_bp.route("/queue", methods=["GET"])
@login_required
def get_review_queue():
    """
    Retrieves list of pending report items awaiting municipal matching review.
    Restricted to municipal officers and administrators.
    """
    if not _is_staff():
        raise ForbiddenError("Access to the incident matching review queue requires municipal staff privileges.")

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    category = request.args.get("category", None)

    queue_data = decision_service.get_review_queue(
        page=page,
        per_page=per_page,
        category=category,
    )

    return jsonify({
        "status": "success",
        "data": queue_data,
    }), 200


@matching_bp.route("/confirm-link", methods=["POST"])
@login_required
def confirm_link():
    """
    Officially links a ReportItem to an existing canonical Incident.
    Restricted to municipal officers and administrators.
    """
    if not _is_staff():
        raise ForbiddenError("Confirming incident links requires municipal staff privileges.")

    data = request.get_json(silent=True) or {}
    report_item_id = data.get("report_item_id")
    incident_id = data.get("incident_id")
    review_notes = data.get("review_notes", "")
    evaluation_id = data.get("evaluation_id")

    if not report_item_id or not incident_id:
        raise ValidationError("Both 'report_item_id' and 'incident_id' are required.")

    result = decision_service.confirm_link_to_incident(
        report_item_id=report_item_id,
        incident_id=incident_id,
        reviewer_id=g.current_user.id,
        review_notes=review_notes,
        evaluation_id=evaluation_id,
    )

    return jsonify({
        "status": "success",
        "message": f"ReportItem '{report_item_id}' successfully linked to Incident '{incident_id}'.",
        "data": result,
    }), 200


@matching_bp.route("/confirm-new", methods=["POST"])
@login_required
def confirm_new_incident():
    """
    Confirms that a ReportItem represents a brand new canonical Incident.
    Restricted to municipal officers and administrators.
    """
    if not _is_staff():
        raise ForbiddenError("Confirming new canonical incidents requires municipal staff privileges.")

    data = request.get_json(silent=True) or {}
    report_item_id = data.get("report_item_id")
    review_notes = data.get("review_notes", "")
    evaluation_id = data.get("evaluation_id")
    severity = data.get("severity")

    if not report_item_id:
        raise ValidationError("'report_item_id' is required.")

    result = decision_service.confirm_new_incident(
        report_item_id=report_item_id,
        reviewer_id=g.current_user.id,
        review_notes=review_notes,
        evaluation_id=evaluation_id,
        severity=severity,
    )

    return jsonify({
        "status": "success",
        "message": f"New canonical incident '{result['incident_reference']}' successfully created.",
        "data": result,
    }), 201


@matching_bp.route("/reject-candidate", methods=["POST"])
@login_required
def reject_candidate():
    """
    Rejects a suggested candidate incident while keeping the report item in the queue.
    Restricted to municipal officers and administrators.
    """
    if not _is_staff():
        raise ForbiddenError("Rejecting candidate matches requires municipal staff privileges.")

    data = request.get_json(silent=True) or {}
    report_item_id = data.get("report_item_id")
    candidate_incident_id = data.get("candidate_incident_id")
    review_notes = data.get("review_notes", "")
    evaluation_id = data.get("evaluation_id")

    if not report_item_id or not candidate_incident_id:
        raise ValidationError("Both 'report_item_id' and 'candidate_incident_id' are required.")

    result = decision_service.reject_candidate(
        report_item_id=report_item_id,
        candidate_incident_id=candidate_incident_id,
        reviewer_id=g.current_user.id,
        review_notes=review_notes,
        evaluation_id=evaluation_id,
    )

    return jsonify({
        "status": "success",
        "message": f"Candidate incident '{candidate_incident_id}' rejected for item '{report_item_id}'.",
        "data": result,
    }), 200


@matching_bp.route("/consolidate-incidents", methods=["POST"])
@login_required
def consolidate_incidents():
    """
    Consolidates two historical canonical incident records that refer to the same defect.
    Restricted to municipal administrators.
    """
    if not _is_staff():
        raise ForbiddenError("Consolidating incident records requires administrator privileges.")

    data = request.get_json(silent=True) or {}
    canonical_incident_id = data.get("canonical_incident_id")
    superseded_incident_id = data.get("superseded_incident_id")
    consolidation_reason = data.get("consolidation_reason", "")

    if not canonical_incident_id or not superseded_incident_id:
        raise ValidationError("Both 'canonical_incident_id' and 'superseded_incident_id' are required.")

    result = consolidation_service.consolidate_incidents(
        canonical_incident_id=canonical_incident_id,
        superseded_incident_id=superseded_incident_id,
        consolidated_by=g.current_user.id,
        consolidation_reason=consolidation_reason,
    )

    return jsonify({
        "status": "success",
        "message": f"Successfully consolidated incident '{superseded_incident_id}' into '{canonical_incident_id}'.",
        "data": result,
    }), 200
