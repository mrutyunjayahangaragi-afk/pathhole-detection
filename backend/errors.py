"""
Centralized Error Handling and Domain Exceptions for CivicLens
==============================================================

Provides standard domain exceptions and Flask error handlers that return
consistent JSON error envelopes without exposing internal stack traces,
paths, or secrets.
"""

import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from flask import Flask, jsonify, request, g


class CivicLensError(Exception):
    """Base exception for all CivicLens domain and service errors."""
    status_code: int = 500
    error_code: str = "INTERNAL_SERVER_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(self, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "error": self.message,
            "error_code": self.error_code,
        }
        if self.details:
            result["details"] = self.details
        return result


class ValidationError(CivicLensError):
    """Raised when client request payload fails validation."""
    status_code = 400
    error_code = "VALIDATION_ERROR"
    message = "Request validation failed."


class NotFoundError(CivicLensError):
    """Raised when a requested resource is not found."""
    status_code = 404
    error_code = "RESOURCE_NOT_FOUND"
    message = "The requested resource was not found."


class UnauthorizedError(CivicLensError):
    """Raised when authentication is missing or invalid."""
    status_code = 401
    error_code = "UNAUTHORIZED"
    message = "Authentication required."


class ForbiddenError(CivicLensError):
    """Raised when the authenticated user does not have permission for the action."""
    status_code = 403
    error_code = "FORBIDDEN"
    message = "Access forbidden."


class ConflictError(CivicLensError):
    """Raised when a state conflict occurs."""
    status_code = 409
    error_code = "CONFLICT"
    message = "The requested operation conflicts with existing resource state."


class DatabaseError(CivicLensError):
    """Raised when an unexpected database error occurs."""
    status_code = 500
    error_code = "DATABASE_ERROR"
    message = "A database operation failed."


def register_error_handlers(app: Flask) -> None:
    """Registers standard HTTP and custom exception handlers on the Flask app."""

    @app.errorhandler(CivicLensError)
    def handle_civiclens_error(error: CivicLensError) -> Tuple[Any, int]:
        return jsonify(error.to_dict()), error.status_code

    @app.errorhandler(400)
    def handle_bad_request(error) -> Tuple[Any, int]:
        msg = getattr(error, "description", "Bad Request")
        return jsonify({"error": msg, "error_code": "BAD_REQUEST"}), 400

    @app.errorhandler(404)
    def handle_not_found(error) -> Tuple[Any, int]:
        return jsonify({"error": "Resource not found", "error_code": "NOT_FOUND"}), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(error) -> Tuple[Any, int]:
        return jsonify({"error": "Method not allowed", "error_code": "METHOD_NOT_ALLOWED"}), 405

    @app.errorhandler(500)
    def handle_internal_error(error) -> Tuple[Any, int]:
        # Log internally, but never expose the stack trace to the client
        app.logger.error(f"Unhandled 500 internal server error: {error}")

        # Record to application_error_events database table
        try:
            from backend.db.engine import get_session_factory
            from backend.db.models import ApplicationErrorEvent

            user_id = None
            if hasattr(g, "current_user") and g.current_user:
                user_id = getattr(g.current_user, "id", None)

            # Sanitize request params
            sanitized_params = {}
            if request:
                for k, v in request.args.items():
                    if any(s in k.lower() for s in ["password", "token", "secret", "auth", "key"]):
                        sanitized_params[k] = "[REDACTED]"
                    else:
                        sanitized_params[k] = str(v)[:200]

            db = get_session_factory()()
            try:
                evt = ApplicationErrorEvent(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.now(timezone.utc),
                    endpoint=request.path if request else None,
                    method=request.method if request else None,
                    user_id=user_id,
                    error_code="INTERNAL_SERVER_ERROR",
                    error_type=error.__class__.__name__ if hasattr(error, "__class__") else "InternalServerError",
                    error_message=str(error)[:1000],
                    traceback=traceback.format_exc()[:4000],
                    sanitized_request_params=sanitized_params,
                    client_ip=request.remote_addr if request else None,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(evt)
                db.commit()
            except Exception as db_err:
                db.rollback()
                app.logger.debug(f"Failed to record ApplicationErrorEvent: {db_err}")
            finally:
                db.close()
        except Exception:
            pass

        return jsonify({
            "error": "An internal server error occurred.",
            "error_code": "INTERNAL_SERVER_ERROR"
        }), 500
