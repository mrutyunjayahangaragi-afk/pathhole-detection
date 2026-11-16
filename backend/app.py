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
from backend.db.init_schema import create_all_tables
from backend.errors import register_error_handlers, ValidationError
from backend.logging_config import setup_logging
from backend.services.incident_service import IncidentService
from backend.services.report_service import ReportService
from backend.services.location_service import LocationService
from backend.routes.auth_routes import auth_bp
from backend.routes.citizen_routes import citizen_bp
from backend.routes.detection_routes import detection_bp
from backend.routes.matching_routes import matching_bp
from backend.routes.language_routes import language_bp
from backend.routes.location_routes import location_bp
from backend.routes.municipal_routes import municipal_bp
from backend.routes.public_routes import public_bp
from backend.routes.notification_routes import notification_bp, citizen_tracking_bp


def create_app(config: Optional[Config] = None) -> Flask:
    """Application factory for CivicLens backend."""
    app = Flask(
        __name__,
        static_folder=os.path.join(_parent, "frontend", "static"),
        static_url_path="/static",
    )
    cfg = config or get_config()
    app.config.from_object(cfg)

    # Initialize structured logging
    logger = setup_logging(cfg.LOG_LEVEL, app_name="civiclens")
    app.logger = logger
    app.config["MAX_CONTENT_LENGTH"] = cfg.MAX_CONTENT_LENGTH

    # Ensure database schema is present
    try:
        from backend.config import redact_secret
        from backend.db.engine import get_engine
        from sqlalchemy import text

        if getattr(cfg, "DATABASE_PROVIDER", "sqlite") in ("supabase", "postgresql"):
            create_all_tables(cfg.DATABASE_URL)
            eng = get_engine(cfg.DATABASE_URL)
            with eng.connect() as conn:
                conn.execute(text("SELECT 1;"))
            logger.info(f"Connected to Supabase PostgreSQL database ({redact_secret(cfg.DATABASE_URL)})")
        else:
            init_db(cfg.DATABASE_PATH)
            create_all_tables(f"sqlite:///{cfg.DATABASE_PATH}")
            logger.info(f"Connected to SQLite database at '{cfg.DATABASE_PATH}'")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        if not cfg.TESTING:
            raise

    # Register centralized error handlers
    register_error_handlers(app)

    # Register API Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(citizen_bp)
    app.register_blueprint(detection_bp)
    app.register_blueprint(matching_bp)
    app.register_blueprint(language_bp)
    app.register_blueprint(location_bp)
    app.register_blueprint(municipal_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(citizen_tracking_bp)

    # Seed default municipal departments if not already present
    try:
        from backend.services.department_management_service import DepartmentManagementService
        DepartmentManagementService().seed_default_departments()
    except Exception as e:
        logger.debug(f"Default departments seed deferred or handled: {e}")

    # Instantiate services
    location_service = LocationService(cfg)
    report_service = ReportService(location_service=location_service, db_path=cfg.DATABASE_PATH)
    incident_service = IncidentService(db_path=cfg.DATABASE_PATH)

    # ---------------------------------------------------------------------------
    # CORS, Security Headers & Preflight
    # ---------------------------------------------------------------------------
    @app.after_request
    def add_security_and_cors_headers(response):
        origins = cfg.CORS_ORIGINS
        req_origin = request.headers.get("Origin")

        if "*" in origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif req_origin and req_origin in origins:
            response.headers["Access-Control-Allow-Origin"] = req_origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        elif origins:
            response.headers["Access-Control-Allow-Origin"] = origins[0]

        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Requested-With, Accept, Origin, Idempotency-Key"
        )

        # Production Hardened Security Headers (Step 10 Audit)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), camera=(self), microphone=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://unpkg.com https://*.basemaps.cartocdn.com; "
            "connect-src 'self'; "
            "frame-ancestors 'self';"
        )
        if request.is_secure or getattr(cfg, "ENV", "") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Asset and API Caching
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
        elif request.path.startswith("/api/"):
            if "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

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
        """Health check endpoint with operational diagnostics and live DB ping."""
        db_status = "connected"
        try:
            from backend.db.engine import get_engine
            from sqlalchemy import text
            eng = get_engine()
            with eng.connect() as conn:
                conn.execute(text("SELECT 1;"))
        except Exception as e:
            db_status = f"unhealthy: {e}"

        is_healthy = db_status == "connected"
        return jsonify({
            "status": "ok" if is_healthy else "degraded",
            "environment": cfg.ENV,
            "version": "0.4.0-civiclens",
            "database": db_status,
            "database_provider": getattr(cfg, "DATABASE_PROVIDER", "sqlite"),
            "database_status": db_status,
        }), (200 if is_healthy else 503)

    @app.route("/api/config", methods=["GET"])
    @app.route("/api/v1/config", methods=["GET"])
    def get_public_config():
        """Returns public client configuration (e.g. map settings)."""
        cfg = get_config()
        return jsonify({
            "status": "ok",
            "carto_api_key": getattr(cfg, "CARTO_API_KEY", ""),
            "dedup_radius_meters": getattr(cfg, "DEDUP_RADIUS_METERS", 15.0),
            "environment": cfg.ENV,
        }), 200

    # ---------------------------------------------------------------------------
    # Frontend & Dashboard static file serving
    # ---------------------------------------------------------------------------
    @app.route("/", methods=["GET"])
    def serve_index():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), "index.html")

    @app.route("/dashboard", methods=["GET"])
    @app.route("/dashboard/", methods=["GET"])
    def serve_dashboard():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "dashboard"), "dashboard.html")

    @app.route("/dashboard/<path:filename>", methods=["GET"])
    def serve_dashboard_files(filename):
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "dashboard"), filename)

    @app.route("/frontend/<path:filename>", methods=["GET"])
    def serve_frontend_files(filename):
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), filename)

    @app.route("/municipal/<path:filename>", methods=["GET"])
    def serve_municipal_files(filename):
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend", "municipal"), filename)

    @app.route("/citizen-report.html", methods=["GET"])
    @app.route("/citizen-report", methods=["GET"])
    def serve_citizen_report():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), "citizen-report.html")

    @app.route("/citizen-login.html", methods=["GET"])
    @app.route("/citizen-login", methods=["GET"])
    def serve_citizen_login():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), "citizen-login.html")

    @app.route("/citizen-dashboard.html", methods=["GET"])
    @app.route("/citizen-dashboard", methods=["GET"])
    def serve_citizen_dashboard():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), "citizen-dashboard.html")

    @app.route("/my-reports.html", methods=["GET"])
    @app.route("/my-reports", methods=["GET"])
    def serve_my_reports():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), "my-reports.html")

    @app.route("/report-detail.html", methods=["GET"])
    @app.route("/report-detail", methods=["GET"])
    def serve_report_detail():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), "report-detail.html")

    @app.route("/public-map.html", methods=["GET"])
    @app.route("/public-map", methods=["GET"])
    def serve_public_map():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), "public-map.html")

    @app.route("/public-incident.html", methods=["GET"])
    @app.route("/public-incident", methods=["GET"])
    def serve_public_incident():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), "public-incident.html")

    @app.route("/notifications.html", methods=["GET"])
    @app.route("/notifications", methods=["GET"])
    def serve_notifications():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), "notifications.html")

    @app.route("/transparency.html", methods=["GET"])
    @app.route("/transparency", methods=["GET"])
    def serve_transparency():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend"), "transparency.html")

    @app.route("/match-review.html", methods=["GET"])
    @app.route("/match-review", methods=["GET"])
    def serve_match_review():
        from flask import send_from_directory
        return send_from_directory(os.path.join(_parent, "frontend", "municipal"), "match-review.html")

    return app


# Default application instance for WSGI runners and python app.py
app = create_app()

if __name__ == "__main__":
    cfg = get_config()
    app.run(host=cfg.HOST, port=cfg.PORT, debug=cfg.DEBUG)
