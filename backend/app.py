"""
Pothole Reporting Backend — CivicLens Foundation
=================================================

REST API that receives detection records from onboard vehicle units and citizen reports,
deduplicates reports of the same physical pothole, reverse-geocodes locations,
and serves aggregated data to the municipal dashboard.

Maintains 100% backward compatibility with Roadstate API contracts while
delegating business logic to clean application services.
"""

import sys
from pathlib import Path
_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

import os
from typing import Optional
from flask import Flask, request, jsonify

from backend.config import Config, get_config
from backend.database import init_db
from backend.errors import register_error_handlers, ValidationError
from backend.logging_config import setup_logging
from backend.services.incident_service import IncidentService
from backend.services.report_service import ReportService
from backend.services.location_service import LocationService


def create_app(config: Optional[Config] = None) -> Flask:
    """Application factory for CivicLens backend."""
    app = Flask(__name__)
    cfg = config or get_config()
    app.config.from_object(cfg)

    # Initialize structured logging
    logger = setup_logging(cfg.LOG_LEVEL, app_name="civiclens")
    app.logger = logger

    # Ensure database schema is present
    try:
        init_db(cfg.DATABASE_PATH)
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        if not cfg.TESTING:
            raise

    # Register centralized error handlers
    register_error_handlers(app)

    # Instantiate services
    location_service = LocationService(cfg)
    report_service = ReportService(location_service=location_service, db_path=cfg.DATABASE_PATH)
    incident_service = IncidentService(db_path=cfg.DATABASE_PATH)

    # ---------------------------------------------------------------------------
    # CORS & Preflight
    # ---------------------------------------------------------------------------
    @app.after_request
    def add_cors_headers(response):
        origins = cfg.CORS_ORIGINS
        origin_header = "*" if "*" in origins else ", ".join(origins)
        response.headers["Access-Control-Allow-Origin"] = origin_header
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    @app.before_request
    def handle_options_preflight():
        if request.method == "OPTIONS":
            return "", 204

    # ---------------------------------------------------------------------------
    # Routes
    # ---------------------------------------------------------------------------
    @app.route("/api/detections", methods=["POST"])
    def submit_detection():
        """
        Ingests a detection report from a vehicle or citizen.
        Body:
        {
          "vehicle_id": "bus-042",
          "latitude": 8.5241,
          "longitude": 76.9366,
          "severity": "moderate",
          "est_depth_cm": 3.2,
          "confidence": 0.87,
          "image_ref": "s3://bucket/frame123.jpg"   # optional
        }
        """
        data = request.get_json(force=True, silent=True) or {}
        result, status_code = report_service.process_detection_report(data)
        return jsonify(result), status_code

    @app.route("/api/detections", methods=["GET"])
    def list_detections():
        """
        Query params:
          severity=minor|moderate|severe   filter by severity
          status=reported|acknowledged...  filter by status
          limit=200                        max rows (default 200)
          offset=0                         pagination offset
        """
        severity = request.args.get("severity")
        status = request.args.get("status")

        try:
            limit = int(request.args.get("limit", 200))
        except ValueError:
            raise ValidationError("limit must be a valid integer")

        try:
            offset = int(request.args.get("offset", 0))
        except ValueError:
            raise ValidationError("offset must be a valid integer")

        results = incident_service.list_incidents(
            severity=severity, status=status, limit=limit, offset=offset
        )
        return jsonify(results)

    @app.route("/api/detections/<detection_id>", methods=["GET"])
    def get_detection(detection_id):
        """Retrieves a single detection by ID."""
        return jsonify(incident_service.get_incident_by_id(detection_id))

    @app.route("/api/detections/<detection_id>", methods=["PATCH"])
    def update_detection(detection_id):
        """Body: {"status": "acknowledged"} — updates status of detection/incident."""
        data = request.get_json(force=True, silent=True) or {}
        new_status = data.get("status")
        if not new_status:
            raise ValidationError("Missing required field 'status'")
        return jsonify(incident_service.update_incident_status(detection_id, new_status))

    @app.route("/api/stats", methods=["GET"])
    def stats():
        """Returns aggregate municipal statistics."""
        return jsonify(incident_service.get_statistics())

    @app.route("/api/health", methods=["GET"])
    def health():
        """Health check endpoint with operational diagnostics."""
        return jsonify({
            "status": "ok",
            "environment": cfg.ENV,
            "version": "0.2.0-baseline",
            "database": "connected",
        })

    return app


# Default application instance for WSGI runners and python app.py
app = create_app()

if __name__ == "__main__":
    cfg = get_config()
    app.run(host=cfg.HOST, port=cfg.PORT, debug=cfg.DEBUG)
