"""
Location Intelligence API Routes
================================
Provides endpoints for safe, rate-limited reverse geocoding,
and structured geographic context retrieval.
"""

from flask import Blueprint, request, jsonify, g
from backend.services.location_intelligence_service import LocationIntelligenceService
from backend.auth import login_required
from backend.db.engine import get_session_factory
from backend.db.models import LocationRecord, CitizenReport
from backend.errors import ValidationError, NotFoundError

location_bp = Blueprint("location_bp", __name__, url_prefix="/api/v1/location")
location_service = LocationIntelligenceService()


@location_bp.route("/reverse-geocode", methods=["POST"])
def reverse_geocode():
    """
    Reverse-geocodes map coordinates into structured address components.
    Guarantees Nominatim rate-limiting compliance (1.0s interval) and caching.
    """
    data = request.get_json(silent=True) or {}
    lat = data.get("latitude")
    lon = data.get("longitude")
    language = data.get("language", "en")

    if lat is None or lon is None:
        raise ValidationError("Both latitude and longitude are required.")

    res = location_service.reverse_geocode_structured(lat, lon, language)
    return jsonify({
        "status": "success",
        "location": res.to_dict(),
    }), 200


@location_bp.route("/context/<report_id>", methods=["GET"])
@login_required
def get_location_context(report_id):
    """
    Retrieves structured location provenance and address components for a report.
    """
    db = get_session_factory()()
    try:
        report = db.query(CitizenReport).filter_by(id=report_id).first()
        if not report:
            raise NotFoundError("Report not found")

        is_staff = g.current_user.role in ("municipal_officer", "dept_admin", "system_admin")
        if report.citizen_id != g.current_user.id and not is_staff:
            raise NotFoundError("Report not found or access denied")

        loc = db.query(LocationRecord).filter_by(report_id=report_id).first()
        if not loc:
            return jsonify({
                "status": "success",
                "report_id": report_id,
                "location_record": None,
                "coordinates": {"latitude": report.latitude, "longitude": report.longitude},
            }), 200

        return jsonify({
            "status": "success",
            "report_id": report_id,
            "coordinates": {"latitude": loc.latitude, "longitude": loc.longitude},
            "location_record": {
                "road_name": loc.road_name,
                "road_type": loc.road_type,
                "locality": loc.locality,
                "suburb": loc.suburb,
                "city": loc.city,
                "district": loc.district,
                "state": loc.state,
                "postal_code": loc.postal_code,
                "country": loc.country,
                "normalized_address": loc.normalized_address,
                "location_source": loc.location_source,
                "location_accuracy_m": loc.location_accuracy_m,
                "geocoding_provider": loc.geocoding_provider,
                "geocoding_status": loc.geocoding_status,
                "geocoded_at": loc.geocoded_at.isoformat() if loc.geocoded_at else None,
            },
        }), 200
    finally:
        db.close()
