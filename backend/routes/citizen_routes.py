"""
Citizen Grievance Reporting Routes
==================================
Provides endpoints for complaint submission, evidence upload,
report portfolio querying, and private evidence streaming.
"""

from flask import Blueprint, request, jsonify, g, send_file
from backend.services.citizen_report_service import CitizenReportService
from backend.services.multilingual_search_service import MultilingualSearchService
from backend.auth import login_required
from backend.errors import ValidationError

citizen_bp = Blueprint("citizen_bp", __name__, url_prefix="/api/v1")
report_service = CitizenReportService()
search_service = MultilingualSearchService()


@citizen_bp.route("/reports", methods=["POST"])
@login_required
def submit_report():
    """
    Submits a new civic grievance report.
    Supports both multipart/form-data (with file uploads) and application/json.
    """
    idempotency_key = request.headers.get("Idempotency-Key") or request.form.get("idempotency_key")
    evidence_files = []

    if request.content_type and "multipart/form-data" in request.content_type:
        title = request.form.get("title")
        description = request.form.get("description")
        category = request.form.get("category", "pothole")
        severity = request.form.get("severity", "minor")
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        address = request.form.get("address")
        original_language = request.form.get("original_language", "en")
        is_manual = request.form.get("is_manual_location", "").lower() in ("1", "true", "yes")

        acc_str = request.form.get("location_accuracy_m")
        location_accuracy_m = float(acc_str) if acc_str and acc_str.strip() else None

        # Extract file uploads
        uploaded = request.files.getlist("evidence") or request.files.getlist("photos")
        for f in uploaded:
            if f and f.filename:
                evidence_files.append({
                    "filename": f.filename,
                    "content_bytes": f.read(),
                    "mime_type": f.mimetype or "image/jpeg",
                })
    else:
        data = request.get_json(silent=True) or {}
        title = data.get("title")
        description = data.get("description")
        category = data.get("category", "pothole")
        severity = data.get("severity", "minor")
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        address = data.get("address")
        original_language = data.get("original_language", "en")
        is_manual = bool(data.get("is_manual_location", False))
        location_accuracy_m = data.get("location_accuracy_m")
        if not idempotency_key:
            idempotency_key = data.get("idempotency_key")

    result = report_service.create_report(
        citizen_id=g.current_user.id,
        title=title,
        description=description,
        category=category,
        severity=severity,
        latitude=latitude,
        longitude=longitude,
        location_accuracy_m=location_accuracy_m,
        is_manual_location=is_manual,
        address=address,
        original_language=original_language,
        idempotency_key=idempotency_key,
        evidence_files=evidence_files,
    )

    return jsonify({
        "status": "success",
        "message": "Report submitted successfully",
        "report": result,
    }), 201


@citizen_bp.route("/reports", methods=["GET"])
@login_required
def list_reports():
    """Returns the authenticated citizen's submitted reports with filters and pagination."""
    status = request.args.get("status")
    category = request.args.get("category")
    search = request.args.get("search")

    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
    except ValueError:
        page, per_page = 1, 10

    results = report_service.list_citizen_reports(
        citizen_id=g.current_user.id,
        status=status,
        category=category,
        search=search,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        "status": "success",
        **results,
    }), 200


@citizen_bp.route("/reports/search", methods=["GET"])
@login_required
def search_reports():
    """
    Multilingual search across reports matching Kannada, English, or translated text.
    Scoped by citizen ownership or municipal officer role.
    """
    query = request.args.get("q") or request.args.get("query")
    category = request.args.get("category")
    status = request.args.get("status")
    language = request.args.get("language")

    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
    except ValueError:
        page, per_page = 1, 20

    results = search_service.search_reports(
        query=query,
        category=category,
        status=status,
        language=language,
        requesting_user=g.current_user,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        "status": "success",
        **results,
    }), 200


@citizen_bp.route("/reports/<report_id>", methods=["GET"])
@login_required
def get_report_detail(report_id):
    """Retrieves full details of an individual report owned by the citizen."""
    report = report_service.get_citizen_report(
        report_id=report_id, citizen_id=g.current_user.id
    )
    return jsonify({
        "status": "success",
        "report": report,
    }), 200


@citizen_bp.route("/evidence/<asset_id>", methods=["GET"])
@login_required
def get_evidence_file(asset_id):
    """Serves private evidence asset file with strict permission verification."""
    is_staff = g.current_user.role in ("municipal_officer", "dept_admin", "system_admin")
    file_path, mime_type = report_service.get_evidence_file(
        asset_id=asset_id,
        requesting_user_id=g.current_user.id,
        is_admin_or_officer=is_staff,
    )
    return send_file(file_path, mimetype=mime_type)
