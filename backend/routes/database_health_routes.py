"""
Database Health Routes
======================
Sanitized health, readiness, and liveness endpoints for operational monitoring.
"""

from flask import Blueprint, jsonify
from backend.services.database_health_service import DatabaseHealthService

health_diag_bp = Blueprint("health_diagnostics", __name__, url_prefix="/api/health")
health_service = DatabaseHealthService()


@health_diag_bp.route("/live", methods=["GET"])
def health_live():
    """Liveness probe: returns 200 if process is running."""
    res = health_service.get_liveness()
    return jsonify(res), 200


@health_diag_bp.route("/ready", methods=["GET"])
def health_ready():
    """Readiness probe: returns 200 if database is reachable, 503 if not."""
    res = health_service.get_readiness()
    status_code = 200 if res.get("status") == "ready" else 503
    return jsonify(res), status_code


@health_diag_bp.route("/database", methods=["GET"])
def health_database():
    """Sanitized database diagnostics for administration and monitoring."""
    res = health_service.get_database_diagnostics()
    return jsonify(res), 200
