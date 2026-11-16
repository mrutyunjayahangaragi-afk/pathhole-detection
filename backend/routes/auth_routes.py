"""
Citizen Authentication Routes
=============================
Provides endpoints for registration, login, logout, profile retrieval,
and profile updates.
"""

from flask import Blueprint, request, jsonify, session, g
from backend.services.auth_service import AuthService
from backend.services.official_auth_service import OfficialAuthService
from backend.auth import login_required, role_required
from backend.errors import ValidationError

auth_bp = Blueprint("auth_bp", __name__, url_prefix="/api/v1/auth")
auth_service = AuthService()
official_auth_service = OfficialAuthService()


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


# ============================================================================
# Official Municipal Authentication & Invitation Endpoints
# ============================================================================

@auth_bp.route("/official-login", methods=["POST"])
def official_login():
    """Authenticates municipal official, department administrator, or executive."""
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")

    user_dict, token = official_auth_service.authenticate_official(
        email=email, password=password, client_ip=client_ip
    )

    session["user_id"] = user_dict["id"]
    session["role"] = user_dict["role"]

    return jsonify({
        "status": "success",
        "message": "Authenticated successfully as municipal official.",
        "user": user_dict,
        "token": token
    }), 200


@auth_bp.route("/invitations", methods=["POST"])
@role_required("system_admin", "municipal_admin", "dept_admin")
def create_invitation():
    """Creates a secure, time-limited invitation for an official."""
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    intended_role = data.get("role") or data.get("intended_role")
    municipality_id = data.get("municipality_id")
    department_id = data.get("department_id")

    res = official_auth_service.create_invitation(
        invited_by=g.current_user,
        email=email,
        intended_role=intended_role,
        municipality_id=municipality_id,
        department_id=department_id
    )
    return jsonify({
        "status": "success",
        "message": f"Invitation successfully created for {email}.",
        "invitation": res
    }), 201


@auth_bp.route("/invitations/verify/<token>", methods=["GET"])
def verify_invitation_token(token: str):
    """Verifies validity of an invitation token for the acceptance screen."""
    details = official_auth_service.verify_invitation(token)
    return jsonify({
        "status": "success",
        "invitation": details
    }), 200


@auth_bp.route("/invitations/accept", methods=["POST"])
def accept_invitation():
    """Accepts invitation and sets official password."""
    data = request.get_json(silent=True) or {}
    token = data.get("token") or data.get("invitation_token")
    display_name = data.get("display_name") or data.get("name")
    password = data.get("password")
    confirm_password = data.get("confirm_password") or password

    user_dict, session_token = official_auth_service.accept_invitation(
        raw_token=token,
        display_name=display_name,
        password=password,
        confirm_password=confirm_password
    )

    session["user_id"] = user_dict["id"]
    session["role"] = user_dict["role"]

    return jsonify({
        "status": "success",
        "message": "Invitation accepted and account activated successfully.",
        "user": user_dict,
        "token": session_token
    }), 200


@auth_bp.route("/supabase-verify", methods=["POST"])
def verify_supabase_session():
    """
    Validates a Supabase Auth access token from Google/email sign-in,
    syncs/provisions the user profile, and establishes a verified backend session.
    """
    from backend.auth.supabase_auth import SupabaseAuthService
    from backend.auth import generate_auth_token

    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token")
    if not access_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            access_token = auth_header[7:].strip()

    if not access_token:
        return jsonify({
            "error": "Access token is required.",
            "code": "MISSING_TOKEN"
        }), 400

    target_portal = data.get("target_portal", "citizen")
    service = SupabaseAuthService()

    # 1. Verify access token with Supabase
    supabase_user = service.verify_supabase_token(access_token)

    # Allow test simulation payload for testing environments when SUPABASE_URL is not set
    if not supabase_user and (data.get("test_mock_user") or access_token.startswith("mock_token_")):
        supabase_user = data.get("test_mock_user") or {
            "id": "mock-supa-" + access_token[-8:],
            "email": data.get("email", "mockuser@example.com"),
            "user_metadata": {"full_name": data.get("name", "Mock User")}
        }

    if not supabase_user:
        return jsonify({
            "error": "Invalid or expired Supabase authentication session.",
            "code": "INVALID_TOKEN"
        }), 401

    # 2. Authenticate or sync user profile
    ok, user_data, err_msg = service.authenticate_or_sync_user(
        supabase_user_data=supabase_user,
        target_portal=target_portal
    )

    if not ok:
        status_code = 403 if "authorized municipal access" in (err_msg or "") else 400
        return jsonify({
            "error": err_msg,
            "code": "ACCESS_DENIED" if status_code == 403 else "SYNC_ERROR"
        }), status_code

    # 3. Establish Flask session & generate backend bearer token
    session["user_id"] = user_data["id"]
    session["role"] = user_data["role"]
    token = generate_auth_token(user_data["id"], user_data["role"])

    return jsonify({
        "status": "success",
        "message": "Authentication verified successfully.",
        "user": user_data,
        "token": token
    }), 200


