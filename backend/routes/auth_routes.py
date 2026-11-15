"""
Citizen Authentication Routes
=============================
Provides endpoints for registration, login, logout, profile retrieval,
and profile updates.
"""

from flask import Blueprint, request, jsonify, session, g
from backend.services.auth_service import AuthService
from backend.auth import login_required
from backend.errors import ValidationError

auth_bp = Blueprint("auth_bp", __name__, url_prefix="/api/v1/auth")
auth_service = AuthService()


@auth_bp.route("/register", methods=["POST"])
def register():
    """Registers a new citizen user."""
    data = request.get_json(silent=True) or {}
    display_name = data.get("display_name") or data.get("name")
    email = data.get("email")
    password = data.get("password")
    confirm_password = data.get("confirm_password") or password
    phone = data.get("phone")
    preferred_language = data.get("preferred_language", "en")

    result = auth_service.register_citizen(
        display_name=display_name,
        email=email,
        password=password,
        confirm_password=confirm_password,
        phone=phone,
        preferred_language=preferred_language,
    )

    # Automatically set session cookie
    session["user_id"] = result["id"]
    session["role"] = result["role"]

    return jsonify({
        "status": "success",
        "message": "Account registered successfully",
        "user": {
            "id": result["id"],
            "display_name": result["display_name"],
            "email": result["email"],
            "phone": result["phone"],
            "role": result["role"],
            "preferred_language": result["preferred_language"],
        },
        "token": result["token"],
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticates citizen credentials with rate limiting."""
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")

    user_dict, token = auth_service.authenticate(
        email=email, password=password, client_ip=client_ip
    )

    # Store user in session
    session["user_id"] = user_dict["id"]
    session["role"] = user_dict["role"]

    return jsonify({
        "status": "success",
        "message": "Logged in successfully",
        "user": user_dict,
        "token": token,
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Clears the active session."""
    session.clear()
    return jsonify({
        "status": "success",
        "message": "Logged out successfully"
    }), 200


@auth_bp.route("/me", methods=["GET"])
@login_required
def get_current_user_profile():
    """Returns profile and real incident count statistics for the authenticated user."""
    profile = auth_service.get_profile_and_stats(g.current_user.id)
    stats = profile.get("stats", {})
    # Provide normalized keys for frontend dashboard convenience
    normalized_stats = {
        "total": stats.get("total_reports", 0),
        "total_reports": stats.get("total_reports", 0),
        "submitted": stats.get("awaiting_review", 0),
        "awaiting_review": stats.get("awaiting_review", 0),
        "under_review": stats.get("under_review", 0),
        "acknowledged": stats.get("acknowledged", 0),
        "resolved": stats.get("resolved", 0),
    }
    return jsonify({
        "status": "success",
        "user": profile,
        "report_stats": normalized_stats,
    }), 200


@auth_bp.route("/profile", methods=["PATCH", "PUT"])
@login_required
def update_profile():
    """Updates permitted citizen profile fields (name, phone, language)."""
    data = request.get_json(silent=True) or {}
    display_name = data.get("display_name")
    phone = data.get("phone") if "phone" in data else data.get("phone_number")
    preferred_language = data.get("preferred_language")

    updated = auth_service.update_profile(
        user_id=g.current_user.id,
        display_name=display_name,
        phone=phone,
        preferred_language=preferred_language,
    )

    return jsonify({
        "status": "success",
        "message": "Profile updated successfully",
        "user": updated,
    }), 200
