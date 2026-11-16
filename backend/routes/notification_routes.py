"""
CivicLens Notifications, Citizen Tracking & Incident Follow Routes
==================================================================
Handles in-app notifications, preferences, push subscriptions,
independent citizen grievance tracking, and incident follow watchlists.
"""

from flask import Blueprint, request, jsonify, g

from backend.auth import login_required, get_current_user
from backend.services.in_app_notification_service import InAppNotificationService
from backend.services.notification_preference_service import NotificationPreferenceService
from backend.services.incident_follow_service import IncidentFollowService
from backend.db.engine import get_session_factory
from backend.db.models import CitizenReport, ReportItem, Incident, WebPushSubscription

notification_bp = Blueprint("notification_bp", __name__, url_prefix="/api/v2/notifications")
citizen_tracking_bp = Blueprint("citizen_tracking_bp", __name__, url_prefix="/api/v2/citizens")

notif_service = InAppNotificationService()
pref_service = NotificationPreferenceService()
follow_service = IncidentFollowService()


# ============================================================================
# In-App Notifications & Preference Management
# ============================================================================

@notification_bp.route("", methods=["GET"])
@login_required
def get_notifications():
    """Retrieves paginated in-app notifications for the authenticated user."""
    user = get_current_user()
    try:
        page = int(request.args.get("page", "1"))
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        page, limit = 1, 20

    is_read_param = request.args.get("is_read")
    is_read = None
    if is_read_param is not None:
        is_read = is_read_param.lower() in ("true", "1")

    category = request.args.get("category")

    data = notif_service.get_user_notifications(
        user_id=user.id,
        is_read=is_read,
        category=category,
        page=page,
        limit=limit,
    )
    return jsonify(data), 200


@notification_bp.route("/unread-count", methods=["GET"])
@login_required
def get_unread_count():
    """Returns unread notification badge count."""
    user = get_current_user()
    count = notif_service.get_unread_count(user.id)
    return jsonify({"status": "success", "unread_count": count}), 200


@notification_bp.route("/<id>/read", methods=["POST"])
@login_required
def mark_notification_read(id: str):
    """Marks a single notification as read (anti-IDOR protected)."""
    user = get_current_user()
    try:
        res = notif_service.mark_as_read(user.id, id)
        return jsonify(res), 200
    except PermissionError as e:
        return jsonify({"status": "error", "message": str(e)}), 403


@notification_bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_notifications_read():
    """Marks all unread notifications as read for the user."""
    user = get_current_user()
    res = notif_service.mark_all_as_read(user.id)
    return jsonify(res), 200


@notification_bp.route("/preferences", methods=["GET"])
@login_required
def get_preferences():
    """Retrieves current notification preferences for the user."""
    user = get_current_user()
    prefs = pref_service.get_or_create_preferences(user.id)
    return jsonify({"status": "success", "preferences": prefs}), 200


@notification_bp.route("/preferences", methods=["PUT"])
@login_required
def update_preferences():
    """Updates notification channels and quiet hour preferences."""
    user = get_current_user()
    data = request.get_json() or {}
    prefs = pref_service.update_preferences(user.id, data)
    return jsonify({"status": "success", "preferences": prefs}), 200


@notification_bp.route("/push/subscribe", methods=["POST"])
@login_required
def register_push_subscription():
    """Registers a browser Web Push subscription for the authenticated user."""
    user = get_current_user()
    data = request.get_json() or {}

    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        return jsonify({"status": "error", "message": "Missing endpoint, p256dh or auth in push subscription payload."}), 400

    factory = get_session_factory()
    db = factory()
    try:
        existing = db.query(WebPushSubscription).filter_by(user_id=user.id, endpoint=endpoint).first()
        if not existing:
            sub = WebPushSubscription(
                user_id=user.id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
                user_agent=request.headers.get("User-Agent", "")[:255],
            )
            db.add(sub)
            db.commit()
        return jsonify({"status": "success", "message": "Push subscription registered."}), 200
    finally:
        db.close()


@notification_bp.route("/push/unsubscribe", methods=["POST"])
@login_required
def unregister_push_subscription():
    """Removes a browser Web Push subscription."""
    user = get_current_user()
    data = request.get_json() or {}
    endpoint = data.get("endpoint")
    if not endpoint:
        return jsonify({"status": "error", "message": "endpoint is required."}), 400

    factory = get_session_factory()
    db = factory()
    try:
        sub = db.query(WebPushSubscription).filter_by(user_id=user.id, endpoint=endpoint).first()
        if sub:
            db.delete(sub)
            db.commit()
        return jsonify({"status": "success", "message": "Push subscription removed."}), 200
    finally:
        db.close()


# ============================================================================
# Citizen Grievance Tracking & Incident Watchlists
# ============================================================================

@citizen_tracking_bp.route("/reports/<id>/tracking", methods=["GET"])
@login_required
def track_citizen_report(id: str):
    """
    Returns authenticated grievance tracking information.
    Preserves independent CitizenReport status distinct from canonical Incident status.
    Anti-IDOR: ensures citizen can only track their own submitted reports.
    """
    user = get_current_user()
    factory = get_session_factory()
    db = factory()
    try:
        rep = db.query(CitizenReport).filter_by(id=id).first()
        if not rep:
            return jsonify({"status": "error", "message": "Report not found."}), 404

        # Anti-IDOR check
        if rep.citizen_id != user.id and getattr(user, "role", "citizen") == "citizen":
            return jsonify({"status": "error", "message": "Access denied. You can only track your own reports."}), 403

        # Associated canonical incident (if consolidated/matched)
        canonical_info = None
        item = db.query(ReportItem).filter_by(report_id=rep.id).first()
        if item and item.incident_id:
            inc = db.query(Incident).filter_by(id=item.incident_id).first()
            if inc:
                pub = inc.publication
                canonical_info = {
                    "incident_id": inc.id,
                    "incident_reference": inc.incident_reference or f"INC-{inc.id[:8].upper()}",
                    "canonical_status": inc.status,
                    "is_public": (pub.visibility_status == "PUBLIC") if pub else (inc.status not in ["new", "rejected"]),
                    "public_location": (pub.public_location_name if pub and pub.public_location_name else inc.address) or "Civic Area",
                }

        return jsonify({
            "status": "success",
            "report": {
                "id": rep.id,
                "report_reference": rep.report_reference or f"REP-{rep.id[:8].upper()}",
                "report_status": rep.status,
                "title": rep.title,
                "description": rep.description,
                "category": item.category if item else "pothole",
                "severity": rep.reported_severity or "minor",
                "original_language": rep.original_language or "en",
                "submitted_at": rep.created_at.isoformat() if rep.created_at else None,
                "updated_at": rep.updated_at.isoformat() if rep.updated_at else None,
                "canonical_incident": canonical_info,
            }
        }), 200
    finally:
        db.close()


@citizen_tracking_bp.route("/incidents/<id>/follow", methods=["POST"])
@login_required
def follow_incident_endpoint(id: str):
    """Allows an authenticated citizen to follow an approved public incident."""
    user = get_current_user()
    data = request.get_json() or {}
    channels = data.get("channels", "in_app,email")

    try:
        res = follow_service.follow_incident(user.id, id, channels=channels)
        return jsonify(res), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except PermissionError as e:
        return jsonify({"status": "error", "message": str(e)}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed following incident: {e}"}), 500


@citizen_tracking_bp.route("/incidents/<id>/follow", methods=["DELETE"])
@login_required
def unfollow_incident_endpoint(id: str):
    """Allows an authenticated citizen to stop following an incident."""
    user = get_current_user()
    res = follow_service.unfollow_incident(user.id, id)
    return jsonify(res), 200


@citizen_tracking_bp.route("/incidents/followed", methods=["GET"])
@login_required
def get_followed_incidents_endpoint():
    """Returns the authenticated citizen's followed incidents watchlist."""
    user = get_current_user()
    try:
        page = int(request.args.get("page", "1"))
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        page, limit = 1, 20

    data = follow_service.get_followed_incidents(user.id, page=page, limit=limit)
    return jsonify(data), 200
