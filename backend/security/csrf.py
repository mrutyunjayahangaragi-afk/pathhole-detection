"""
CivicLens CSRF Protection
=========================
Implements double-submit cookie pattern for state-changing API endpoints.
Provides decorators and utilities for CSRF token generation and validation.
"""

import secrets
import hmac
from functools import wraps
from flask import request, jsonify, make_response

CSRF_COOKIE_NAME = "cl_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_TOKEN_LENGTH = 32


def generate_csrf_token() -> str:
    """Generates a cryptographically secure CSRF token."""
    return secrets.token_hex(CSRF_TOKEN_LENGTH)


def validate_csrf_token(request_obj) -> bool:
    """
    Validates CSRF token from request header against the cookie.
    Returns True if valid, False if invalid/missing.
    Skips validation for GET, HEAD, OPTIONS requests (safe methods).
    Also skips CSRF validation for Bearer token authenticated API calls.
    """
    if request_obj.method in ("GET", "HEAD", "OPTIONS"):
        return True

    # Skip CSRF for JSON API calls with Bearer token (stateless REST)
    auth_header = request_obj.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return True

    cookie_token = request_obj.cookies.get(CSRF_COOKIE_NAME)
    header_token = request_obj.headers.get(CSRF_HEADER_NAME)

    if not cookie_token or not header_token:
        return False

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(cookie_token, header_token)


def csrf_protect(f):
    """Decorator to enforce CSRF validation on a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not validate_csrf_token(request):
            return jsonify({
                "error": "CSRF validation failed. Invalid or missing token.",
                "code": "CSRF_INVALID"
            }), 403
        return f(*args, **kwargs)
    return decorated_function


def get_csrf_token_endpoint():
    """Flask endpoint handler that returns a fresh CSRF token in cookie and body."""
    token = generate_csrf_token()
    response = make_response(jsonify({"csrf_token": token, "status": "success"}))
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        httponly=False,  # Accessible to frontend JavaScript for header inclusion
        secure=False,
        samesite="Lax",
        max_age=86400
    )
    return response, 200
