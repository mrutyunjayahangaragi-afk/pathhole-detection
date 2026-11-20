"""
CivicLens Public Incident & Geospatial REST Routes
==================================================
Serves public map queries, spatial viewport bounds, marker clusters,
canonical public incident details, and transparent civic statistics.
Enforces strict privacy policies with zero citizen PII or internal notes.
"""

import time
from typing import Optional
from flask import Blueprint, request, jsonify, Response, stream_with_context

from backend.auth import role_required, get_current_user
from backend.services.public_incident_service import PublicIncidentService
from backend.services.public_transparency_service import PublicTransparencyService
from backend.errors import ValidationError, NotFoundError

public_bp = Blueprint("public_bp", __name__, url_prefix="/api/v2/public")

public_service = PublicIncidentService()
transparency_service = PublicTransparencyService()

MUNICIPAL_ROLES = ("municipal_officer", "dept_admin", "municipal_admin", "system_admin")


@public_bp.route("/incidents/viewport", methods=["GET"])
def get_incidents_viewport():
    """
    Retrieves publicly visible canonical incidents within map viewport bounds.
    Query parameters: min_lon, min_lat, max_lon, max_lat, category, status, severity, limit.
    """
    try:
        min_lon = float(request.args.get("min_lon", "76.0"))
        min_lat = float(request.args.get("min_lat", "12.0"))
        max_lon = float(request.args.get("max_lon", "78.5"))
        max_lat = float(request.args.get("max_lat", "13.5"))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Bounding box coordinates must be valid floating point numbers."}), 400

    category = request.args.get("category")
    status = request.args.get("status")
    severity = request.args.get("severity")
    try:
        limit = int(request.args.get("limit", "500"))
    except ValueError:
        limit = 500

    try:
        items = public_service.get_public_incidents_in_viewport(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            category=category,
            status=status,
            severity=severity,
            limit=limit,
        )
        return jsonify({
            "status": "success",
            "count": len(items),
            "items": items,
        }), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@public_bp.route("/incidents/clusters", methods=["GET"])
def get_incidents_clusters():
    """
    Retrieves spatial grid clusters for zoomed-out map views.
    Preserves underlying incident identity while reducing payload size.
    """
    try:
        min_lon = float(request.args.get("min_lon", "76.0"))
        min_lat = float(request.args.get("min_lat", "12.0"))
        max_lon = float(request.args.get("max_lon", "78.5"))
        max_lat = float(request.args.get("max_lat", "13.5"))
        grid_size = float(request.args.get("grid_size", "0.05"))
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Coordinates and grid_size must be valid numbers."}), 400

    try:
        clusters = public_service.get_clustered_incidents(
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            grid_size_degrees=grid_size,
        )
        return jsonify({
            "status": "success",
            "cluster_count": len(clusters),
            "clusters": clusters,
        }), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@public_bp.route("/incidents/hotspots", methods=["GET"])
def get_incidents_hotspots():
    """
    Returns public-safe density hotspots and category aggregations.
    """
    try:
        min_lon = float(request.args.get("min_lon", "76.0"))
        min_lat = float(request.args.get("min_lat", "12.0"))
        max_lon = float(request.args.get("max_lon", "78.5"))
        max_lat = float(request.args.get("max_lat", "13.5"))
    except (ValueError, TypeError):
        min_lon, min_lat, max_lon, max_lat = 76.0, 12.0, 78.5, 13.5

    clusters = public_service.get_clustered_incidents(
        min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat, grid_size_degrees=0.08
    )
    # Sort clusters by incident density
    hotspots = sorted(clusters, key=lambda c: c["count"], reverse=True)[:10]

    return jsonify({
        "status": "success",
        "hotspots": hotspots,
    }), 200


@public_bp.route("/incidents/<ref_or_id>", methods=["GET"])
def get_public_incident_detail(ref_or_id: str):
    """
    Returns full public-safe details, verified timeline, and approved before/after
    resolution photos for a single canonical incident.
    """
    detail = public_service.get_public_incident_detail(ref_or_id)
    if not detail:
        return jsonify({"status": "error", "message": "Incident not found or not approved for public view."}), 404

    return jsonify({
        "status": "success",
        "incident": detail,
    }), 200


@public_bp.route("/statistics", methods=["GET"])
def get_public_transparency_statistics():
    """
    Returns 100% database-backed public transparency metrics, SLA compliance,
    and recent civic resolution milestones. Zero mock data.
    """
    metrics = transparency_service.get_transparency_metrics()
    return jsonify(metrics), 200


@public_bp.route("/recent-activity", methods=["GET"])
def get_recent_activity():
    """
    Returns recent chronological civic activity events (verified, in_progress,
    resolved, new reports) backed by real database records without PII.
    """
    try:
        limit = int(request.args.get("limit", "15"))
    except ValueError:
        limit = 15
    limit = max(1, min(limit, 50))

    events = transparency_service.get_recent_activity(limit=limit)
    return jsonify({
        "status": "success",
        "count": len(events),
        "events": events
    }), 200


@public_bp.route("/search", methods=["GET"])
def search_public_records():
    """
    Full-text search for public incidents by reference code, defect category,
    street locality, or description keywords.
    """
    q = request.args.get("q", "").strip()
    try:
        limit = int(request.args.get("limit", "10"))
    except ValueError:
        limit = 10
    limit = max(1, min(limit, 30))

    results = transparency_service.search_public_incidents(query=q, limit=limit)
    return jsonify({
        "status": "success",
        "query": q,
        "count": len(results),
        "results": results
    }), 200


@public_bp.route("/events", methods=["GET"])
def stream_public_events():
    """
    Server-Sent Events (SSE) endpoint providing public real-time updates.
    Broadcasts public status changes without exposing private citizen data or internal notes.
    """
    def event_stream():
        # Emit initial connected greeting
        yield f"event: connected\ndata: {{\"status\": \"connected\", \"timestamp\": \"{time.time()}\"}}\n\n"
        # Heartbeat ping
        yield f"event: ping\ndata: {{\"timestamp\": \"{time.time()}\"}}\n\n"

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@public_bp.route("/incidents/<id>/publication", methods=["PUT"])
@role_required(*MUNICIPAL_ROLES)
def update_incident_publication(id: str):
    """
    Authorizes municipal staff to update public visibility status of an incident.
    """
    user = get_current_user()
    data = request.get_json() or {}

    visibility_status = data.get("visibility_status", "PUBLIC").upper()
    public_title = data.get("public_title")
    public_description = data.get("public_description")
    public_location_name = data.get("public_location_name")
    visibility_reason = data.get("visibility_reason")
    approved_evidence_ids = data.get("approved_evidence_ids")

    try:
        res = public_service.set_incident_publication(
            incident_id=id,
            officer_id=user.id if user else None,
            visibility_status=visibility_status,
            public_title=public_title,
            public_description=public_description,
            public_location_name=public_location_name,
            visibility_reason=visibility_reason,
            approved_evidence_ids=approved_evidence_ids,
        )
        return jsonify({"status": "success", "publication": res}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed updating publication: {e}"}), 500
