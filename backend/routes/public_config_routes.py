"""
Public Configuration Routes
===========================
Provides browser-safe runtime configuration for static frontend pages (Supabase Auth, branding, diagnostics).
Guarantees ZERO exposure of private secrets, database connection strings, passwords, or service-role keys.
"""

from flask import Blueprint, jsonify, current_app, make_response
from backend.config import get_config

public_config_bp = Blueprint("public_config_bp", __name__, url_prefix="/api/public")


@public_config_bp.route("/config", methods=["GET"])
def get_public_config():
    """
    Returns public frontend configuration (Supabase URL, publishable key, readiness status).
    Safe to access unauthenticated.
    """
    try:
        cfg = current_app.config
        supabase_url = cfg.get("SUPABASE_URL", "")
        pub_key = cfg.get("SUPABASE_PUBLISHABLE_KEY") or cfg.get("SUPABASE_ANON_KEY", "")
        env_name = cfg.get("ENV", "development")
    except RuntimeError:
        cfg = get_config()
        supabase_url = cfg.SUPABASE_URL
        pub_key = cfg.SUPABASE_PUBLISHABLE_KEY
        env_name = getattr(cfg, "ENV", "development")

    # Safety sanitizer: Never expose secret or service-role keys
    if pub_key.startswith("sb_secret_") or "service_role" in pub_key.lower():
        pub_key = ""

    # Diagnostic readiness calculation
    diagnostic_code = "READY"
    is_ready = True

    if not supabase_url or not pub_key:
        diagnostic_code = "MISSING_CONFIG"
        is_ready = False
    elif "YOUR_PROJECT_REF" in supabase_url or "YOUR_" in pub_key:
        diagnostic_code = "PLACEHOLDER_CREDENTIALS"
        is_ready = False
    elif not supabase_url.startswith("https://"):
        diagnostic_code = "INVALID_URL_FORMAT"
        is_ready = False

    payload = {
        "status": "success",
        "app_name": "CivicLens",
        "tagline": "Smart Civic Reporting. Transparent City Improvements.",
        "environment": env_name,
        "supabase_ready": is_ready,
        "diagnostic_code": diagnostic_code,
        "supabase_url": supabase_url if is_ready else "",
        "supabase_publishable_key": pub_key if is_ready else "",
    }

    response = make_response(jsonify(payload))
    response.headers["Cache-Control"] = "public, max-age=60"
    return response, 200
