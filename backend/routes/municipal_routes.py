"""
CivicLens Municipal Officer & Administration Routes
===================================================
Provides comprehensive REST endpoints for municipal triage, verification,
department and officer management, status transitions, on-site inspections,
progress tracking, photographic resolution pairing, and internal collaboration.
"""

from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from backend.auth import login_required, role_required, get_current_user
from backend.services.municipal_dashboard_service import MunicipalDashboardService
from backend.services.incident_state_machine_service import IncidentStateMachineService, IncidentStatus
from backend.services.department_management_service import DepartmentManagementService
from backend.services.incident_assignment_service import IncidentAssignmentService
from backend.services.inspection_resolution_service import InspectionResolutionService
from backend.services.municipal_communication_service import MunicipalCommunicationService
from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, CitizenReport, ReportItem, ReportEvidence, EvidenceAsset,
    Detection, MatchCandidate, MatchDecision, User, Department, Municipality
)
from backend.errors import ValidationError, NotFoundError, CivicLensError


municipal_bp = Blueprint("municipal_bp", __name__, url_prefix="/api/v2/municipal")

# Initialize services
dashboard_service = MunicipalDashboardService()
state_machine_service = IncidentStateMachineService()
dept_service = DepartmentManagementService()
assignment_service = IncidentAssignmentService()
inspection_service = InspectionResolutionService()
comm_service = MunicipalCommunicationService()

MUNICIPAL_ROLES = ("municipal_officer", "dept_admin", "municipal_admin", "system_admin")
ADMIN_ROLES = ("dept_admin", "municipal_admin", "system_admin")
MUNICIPAL_ADMIN_ONLY = ("municipal_admin", "system_admin")


# ============================================================================
# 1. Dashboard Metrics & Analytics
# ============================================================================

@municipal_bp.route("/metrics", methods=["GET"])
@role_required(*MUNICIPAL_ROLES)
def get_metrics():
    """Returns 100% database-backed operations statistics and SLA compliance metrics."""
    dept_id = request.args.get("department_id")
    metrics = dashboard_service.get_dashboard_metrics(department_id=dept_id)
    return jsonify(metrics), 200


# ============================================================================
# 2. Incident Triage Queue & Search
# ============================================================================

@municipal_bp.route("/incidents", methods=["GET"])
@role_required(*MUNICIPAL_ROLES)
def list_incidents():
    """Lists canonical incidents with multi-parameter filtering, full-text search, and pagination."""
    dept_id = request.args.get("department_id")
    status = request.args.get("status")
    priority = request.args.get("priority")
    officer_id = request.args.get("officer_id")
    search_q = request.args.get("q")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    data = dashboard_service.list_triage_incidents(
        department_id=dept_id,
        status=status,
        priority=priority,
        officer_id=officer_id,
        search_query=search_q,
        limit=limit,
        offset=offset
    )
    return jsonify(data), 200


@municipal_bp.route("/incidents/<incident_id>", methods=["GET"])
@role_required(*MUNICIPAL_ROLES)
def get_incident_detail(incident_id: str):
    """Retrieves full canonical incident dossier including citizen reports, AI detections, and history."""
    db = get_session_factory()()
    try:
        inc = db.query(Incident).filter_by(id=incident_id).first()
        if not inc:
            raise NotFoundError(f"Incident '{incident_id}' not found.")

        # Linked Citizen Reports & raw evidence
        reports = db.query(CitizenReport).join(
            ReportItem, ReportItem.report_id == CitizenReport.id
        ).filter(ReportItem.incident_id == inc.id).all()
        report_list = []
        for r in reports:
            # Evidence photos
            evidence_junctions = db.query(ReportEvidence).filter_by(report_id=r.id).all()
            ev_list = []
            for j in evidence_junctions:
                ea = db.query(EvidenceAsset).filter_by(id=j.evidence_id).first()
                if ea:
                    ev_list.append({
                        "id": ea.id,
                        "media_type": ea.media_type,
                        "file_size": ea.file_size_bytes,
                        "url": f"/api/v1/evidence/{ea.id}",
                        "created_at": ea.created_at.isoformat() if ea.created_at else None
                    })

            cit_user = db.query(User).filter_by(id=r.citizen_id).first()
            report_list.append({
                "id": r.id,
                "reference": f"CR-{r.id[:8].upper()}",
                "citizen_name": cit_user.display_name if cit_user else "Anonymous Citizen",
                "title": r.title,
                "description": r.description,
                "reported_severity": r.reported_severity,
                "detected_language": r.detected_language,
                "address": r.address,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "status": r.status,
                "evidence": ev_list,
                "created_at": r.created_at.isoformat() if r.created_at else None
            })

        # AI Detections
        detections = db.query(Detection).filter_by(incident_id=inc.id).all()
        det_list = [{
            "id": d.id,
            "defect_type": d.defect_type,
            "confidence": d.confidence,
            "bbox_x": d.bbox_x,
            "bbox_y": d.bbox_y,
            "bbox_width": d.bbox_width,
            "bbox_height": d.bbox_height,
            "severity": d.severity,
            "review_status": d.review_status,
            "created_at": d.created_at.isoformat() if d.created_at else None
        } for d in detections]

        # Lifecycle history (inspections, progress, resolution)
        lifecycle = inspection_service.get_incident_lifecycle_details(inc.id)

        # Assignment history
        assignments = assignment_service.get_assignment_history(inc.id)

        # Internal notes (filtered by caller role)
        user = get_current_user()
        notes = comm_service.list_internal_notes(inc.id, viewer_role=user.role if user else "municipal_officer")

        # Citizen visible updates
        updates = comm_service.list_citizen_updates(inc.id)

        # Department details
        dept = db.query(Department).filter_by(id=inc.department_id).first() if inc.department_id else None
        officer = db.query(User).filter_by(id=inc.assigned_officer_id).first() if inc.assigned_officer_id else None

        ref_id = f"INC-{(inc.created_at or datetime.now(timezone.utc)).strftime('%Y%m')}-{inc.id[:5].upper()}"

        return jsonify({
            "incident": {
                "id": inc.id,
                "reference": inc.incident_reference or ref_id,
                "title": inc.description or f"{inc.category.replace('_', ' ').capitalize()} defect",
                "category": inc.category,
                "status": inc.status,
                "priority": inc.priority or "normal",
                "department_id": inc.department_id,
                "department_name": dept.name if dept else None,
                "department_code": dept.code if dept else None,
                "assigned_officer_id": inc.assigned_officer_id,
                "assigned_officer_name": officer.display_name if officer else None,
                "latitude": inc.latitude,
                "longitude": inc.longitude,
                "created_at": inc.created_at.isoformat() if inc.created_at else None,
                "updated_at": inc.updated_at.isoformat() if inc.updated_at else None
            },
            "citizen_reports": report_list,
            "ai_detections": det_list,
            "inspections": lifecycle.get("inspections", []),
            "progress_updates": lifecycle.get("progress_updates", []),
            "resolution": lifecycle.get("resolution"),
            "assignments": assignments,
            "internal_notes": notes,
            "citizen_updates": updates
        }), 200
    finally:
        db.close()


# ============================================================================
# 3. Incident Lifecycle Transitions & Verification
# ============================================================================

@municipal_bp.route("/incidents/<incident_id>/verify", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def verify_incident(incident_id: str):
    """Verifies an incoming incident, sets confirmed category and priority, and transitions status."""
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "Field verified by municipal staff")
    priority = data.get("priority", "normal")
    confirmed_defect = data.get("confirmed_defect_type")

    user = get_current_user()
    db = get_session_factory()()
    try:
        inc = db.query(Incident).filter_by(id=incident_id).first()
        if not inc:
            raise NotFoundError(f"Incident '{incident_id}' not found.")

        if confirmed_defect:
            inc.category = confirmed_defect.strip()
        if priority in {"low", "normal", "high", "critical"}:
            inc.priority = priority
        db.commit()

        res = state_machine_service.transition_incident(
            incident_id=incident_id,
            new_status=IncidentStatus.VERIFIED,
            actor_id=user.id,
            actor_role=user.role,
            reason=reason
        )
        return jsonify(res), 200
    finally:
        db.close()


@municipal_bp.route("/incidents/<incident_id>/reject", methods=["POST"])
@role_required(*ADMIN_ROLES)
def reject_incident(incident_id: str):
    """Rejects an invalid or non-municipal grievance report with a mandatory audit reason."""
    data = request.get_json(silent=True) or {}
    reason = data.get("reason")
    if not reason or len(reason.strip()) < 5:
        raise ValidationError("A clear rejection reason (at least 5 characters) is required.")

    user = get_current_user()
    res = state_machine_service.transition_incident(
        incident_id=incident_id,
        new_status=IncidentStatus.REJECTED,
        actor_id=user.id,
        actor_role=user.role,
        reason=reason.strip()
    )
    return jsonify(res), 200


@municipal_bp.route("/incidents/<incident_id>/transition", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def transition_incident(incident_id: str):
    """Transitions incident status governed by role permissions and the lifecycle state graph."""
    data = request.get_json(silent=True) or {}
    new_status = data.get("new_status")
    reason = data.get("reason")

    if not new_status:
        raise ValidationError("Target 'new_status' is required.")
    if not reason:
        raise ValidationError("A transition reason is required.")

    user = get_current_user()
    res = state_machine_service.transition_incident(
        incident_id=incident_id,
        new_status=new_status,
        actor_id=user.id,
        actor_role=user.role,
        reason=reason.strip()
    )
    return jsonify(res), 200


# ============================================================================
# 4. Department & Officer Assignment
# ============================================================================

@municipal_bp.route("/incidents/<incident_id>/assign-department", methods=["POST"])
@role_required(*ADMIN_ROLES)
def assign_department(incident_id: str):
    """Routes an incident to a specific municipal department."""
    data = request.get_json(silent=True) or {}
    dept_id = data.get("department_id")
    reason = data.get("reason")
    priority = data.get("priority")

    if not dept_id:
        raise ValidationError("Department ID is required.")

    user = get_current_user()
    res = assignment_service.assign_department(
        incident_id=incident_id,
        department_id=dept_id,
        assigned_by=user.id,
        actor_role=user.role,
        reason=reason,
        priority=priority
    )
    return jsonify(res), 200


@municipal_bp.route("/incidents/<incident_id>/assign-officer", methods=["POST"])
@role_required(*ADMIN_ROLES)
def assign_officer(incident_id: str):
    """Assigns or transfers an incident to an individual officer with mandatory audit reason for reassignment."""
    data = request.get_json(silent=True) or {}
    officer_id = data.get("officer_id")
    reason = data.get("reason")

    if not officer_id:
        raise ValidationError("Target Officer ID is required.")

    user = get_current_user()
    res = assignment_service.assign_officer(
        incident_id=incident_id,
        officer_id=officer_id,
        assigned_by=user.id,
        actor_role=user.role,
        reason=reason
    )
    return jsonify(res), 200


# ============================================================================
# 5. Inspection, Work Progress & Resolution
# ============================================================================

@municipal_bp.route("/incidents/<incident_id>/inspections", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def record_inspection(incident_id: str):
    """Records an on-site physical inspection by a municipal field officer."""
    data = request.get_json(silent=True) or {}
    findings = data.get("findings")
    confirmed_defect_type = data.get("confirmed_defect_type", "pothole")
    condition_rating = data.get("condition_rating", "moderate")
    evidence_asset_id = data.get("evidence_asset_id")
    next_action = data.get("next_action", "schedule_repair")

    user = get_current_user()
    res = inspection_service.record_inspection(
        incident_id=incident_id,
        officer_id=user.id,
        findings=findings,
        confirmed_defect_type=confirmed_defect_type,
        condition_rating=condition_rating,
        evidence_asset_id=evidence_asset_id,
        next_action=next_action
    )
    return jsonify(res), 201


@municipal_bp.route("/incidents/<incident_id>/work-progress", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def record_work_progress(incident_id: str):
    """Records progress milestones, contractor updates, or work holds with mandatory reasons."""
    data = request.get_json(silent=True) or {}
    stage = data.get("stage")
    notes = data.get("notes")
    hold_reason = data.get("hold_reason")

    user = get_current_user()
    res = inspection_service.record_work_progress(
        incident_id=incident_id,
        officer_id=user.id,
        stage=stage,
        notes=notes,
        hold_reason=hold_reason
    )
    return jsonify(res), 201


@municipal_bp.route("/incidents/<incident_id>/resolve", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def resolve_incident(incident_id: str):
    """Records repair resolution with mandatory before/after photographic evidence pairing."""
    data = request.get_json(silent=True) or {}
    resolution_notes = data.get("resolution_notes")
    after_evidence_id = data.get("after_evidence_id")
    before_evidence_id = data.get("before_evidence_id")

    user = get_current_user()
    res = inspection_service.record_resolution(
        incident_id=incident_id,
        resolved_by=user.id,
        resolution_notes=resolution_notes,
        after_evidence_id=after_evidence_id,
        before_evidence_id=before_evidence_id
    )
    return jsonify(res), 200


@municipal_bp.route("/incidents/evidence/upload", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def upload_municipal_evidence():
    """Uploads field evidence (inspection or after-repair photos) returning an evidence asset ID."""
    if "evidence" not in request.files and "photo" not in request.files:
        raise ValidationError("No evidence file provided in request.")

    file_obj = request.files.get("evidence") or request.files.get("photo")
    if not file_obj or not file_obj.filename:
        raise ValidationError("Invalid evidence file.")

    raw_bytes = file_obj.read()
    res = inspection_service.upload_evidence_asset(
        raw_bytes=raw_bytes,
        orig_name=file_obj.filename,
        mime=file_obj.mimetype or "image/jpeg"
    )
    return jsonify(res), 201


# ============================================================================
# 6. Departments & Officer Management
# ============================================================================

@municipal_bp.route("/departments", methods=["GET"])
@role_required(*MUNICIPAL_ROLES)
def list_departments():
    """Lists all municipal departments with active incident and officer workload counts."""
    include_inactive = request.args.get("include_inactive", "").lower() in ("1", "true", "yes")
    depts = dept_service.list_departments(include_inactive=include_inactive)
    return jsonify({"departments": depts}), 200


@municipal_bp.route("/municipalities", methods=["GET"])
@role_required(*MUNICIPAL_ROLES)
def list_municipalities():
    """Lists registered municipalities."""
    db = get_session_factory()()
    try:
        muns = db.query(Municipality).order_by(Municipality.name.asc()).all()
        return jsonify({
            "status": "success",
            "municipalities": [
                {
                    "id": m.id,
                    "name": m.name,
                    "code": m.code,
                    "state": m.state,
                    "status": m.status,
                    "department_count": len(m.departments) if m.departments else 0
                }
                for m in muns
            ]
        }), 200
    finally:
        db.close()


@municipal_bp.route("/departments", methods=["POST"])
@role_required(*MUNICIPAL_ADMIN_ONLY)
def create_department():
    """Creates a new municipal department with code uniqueness validation."""
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    res = dept_service.create_department(
        name=data.get("name"),
        code=data.get("code"),
        description=data.get("description"),
        contact_email=data.get("contact_email"),
        contact_phone=data.get("contact_phone"),
        actor_id=user.id
    )
    return jsonify(res), 201


@municipal_bp.route("/departments/<dept_id>", methods=["GET"])
@role_required(*MUNICIPAL_ROLES)
def get_department(dept_id: str):
    """Retrieves department details with its assigned officer roster."""
    res = dept_service.get_department(dept_id)
    return jsonify(res), 200


@municipal_bp.route("/departments/<dept_id>", methods=["PUT"])
@role_required(*MUNICIPAL_ADMIN_ONLY)
def update_department(dept_id: str):
    """Updates department details with deactivation guards."""
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    res = dept_service.update_department(
        dept_id=dept_id,
        name=data.get("name"),
        description=data.get("description"),
        contact_email=data.get("contact_email"),
        contact_phone=data.get("contact_phone"),
        is_active=data.get("is_active"),
        actor_id=user.id
    )
    return jsonify(res), 200


@municipal_bp.route("/officers", methods=["GET"])
@role_required(*ADMIN_ROLES)
def list_officers():
    """Lists municipal officers with current workload metrics."""
    dept_id = request.args.get("department_id")
    officers = dept_service.list_officers(department_id=dept_id)
    return jsonify({"officers": officers}), 200


@municipal_bp.route("/officers/onboard", methods=["POST"])
@role_required(*MUNICIPAL_ADMIN_ONLY)
def onboard_officer():
    """Onboards a municipal officer, department administrator, or municipal executive."""
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    res = dept_service.onboard_officer(
        display_name=data.get("display_name"),
        email=data.get("email"),
        password=data.get("password"),
        role=data.get("role", "municipal_officer"),
        department_id=data.get("department_id"),
        role_in_dept=data.get("role_in_dept", "officer"),
        actor_id=user.id
    )
    return jsonify(res), 201


# ============================================================================
# 7. Internal Notes & Public Citizen Updates
# ============================================================================

@municipal_bp.route("/incidents/<incident_id>/notes", methods=["GET"])
@role_required(*MUNICIPAL_ROLES)
def list_internal_notes(incident_id: str):
    """Lists internal notes visible to the caller's role."""
    user = get_current_user()
    notes = comm_service.list_internal_notes(incident_id, viewer_role=user.role)
    return jsonify({"notes": notes}), 200


@municipal_bp.route("/incidents/<incident_id>/notes", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def add_internal_note(incident_id: str):
    """Adds an internal note visible ONLY to authorized municipal staff."""
    data = request.get_json(silent=True) or {}
    content = data.get("content")
    audience = data.get("audience", "internal_officers")

    user = get_current_user()
    res = comm_service.add_internal_note(
        incident_id=incident_id,
        author_id=user.id,
        content=content,
        audience=audience
    )
    return jsonify(res), 201


@municipal_bp.route("/incidents/<incident_id>/citizen-updates", methods=["GET"])
def list_citizen_updates(incident_id: str):
    """Lists public updates visible to citizens tracking this incident."""
    updates = comm_service.list_citizen_updates(incident_id)
    return jsonify({"updates": updates}), 200


@municipal_bp.route("/incidents/<incident_id>/citizen-updates", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def publish_citizen_update(incident_id: str):
    """Publishes an official citizen-facing update that appears on public tracking."""
    data = request.get_json(silent=True) or {}
    public_message = data.get("public_message")
    status_label = data.get("status_label", "Status Update")

    user = get_current_user()
    res = comm_service.publish_citizen_update(
        incident_id=incident_id,
        published_by=user.id,
        public_message=public_message,
        status_label=status_label
    )
    return jsonify(res), 201
