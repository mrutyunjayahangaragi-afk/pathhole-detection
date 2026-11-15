"""
CivicLens Citizen Authentication & Profile Service
=================================================

Handles secure registration, password hashing (PBKDF2-SHA256),
brute-force login rate limiting, session authentication, and profile management.
"""

import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from werkzeug.security import generate_password_hash, check_password_hash

from backend.db.engine import get_session_factory
from backend.db.models import User, CitizenReport
from backend.auth import generate_auth_token
from backend.errors import ValidationError, NotFoundError, CivicLensError

# Standard email validation regex
EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}$")

# In-memory sliding window rate limiter: {key: [timestamp1, timestamp2, ...]}
_FAILED_LOGIN_ATTEMPTS: Dict[str, list] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300


class AuthService:
    """Provides user registration, credential verification, and profile management."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def _check_rate_limit(self, key: str):
        now = time.time()
        attempts = _FAILED_LOGIN_ATTEMPTS.get(key, [])
        # Prune old attempts outside the window
        valid_attempts = [t for t in attempts if now - t < LOCKOUT_WINDOW_SECONDS]
        _FAILED_LOGIN_ATTEMPTS[key] = valid_attempts

        if len(valid_attempts) >= MAX_FAILED_ATTEMPTS:
            remaining = int(LOCKOUT_WINDOW_SECONDS - (now - valid_attempts[0]))
            raise ValidationError(
                f"Too many failed login attempts. Account temporarily locked. Please try again in {remaining} seconds."
            )

    def _record_failed_attempt(self, key: str):
        now = time.time()
        attempts = _FAILED_LOGIN_ATTEMPTS.get(key, [])
        attempts.append(now)
        _FAILED_LOGIN_ATTEMPTS[key] = attempts

    def _clear_failed_attempts(self, key: str):
        if key in _FAILED_LOGIN_ATTEMPTS:
            del _FAILED_LOGIN_ATTEMPTS[key]

    def register_citizen(
        self,
        display_name: str,
        email: str,
        password: str,
        confirm_password: str,
        phone: Optional[str] = None,
        preferred_language: str = "en",
    ) -> Dict[str, Any]:
        """Registers a new citizen user with secure password hashing."""
        # 1. Validate display name
        if not display_name or len(display_name.strip()) < 2:
            raise ValidationError("Full name is required and must be at least 2 characters")
        display_name = display_name.strip()

        # 2. Validate email
        if not email or not EMAIL_REGEX.match(email.strip()):
            raise ValidationError("A valid email address is required")
        email = email.strip().lower()

        # 3. Validate password complexity
        if not password or len(password) < 8:
            raise ValidationError("Password must be at least 8 characters long")
        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise ValidationError("Password must contain at least one letter and one number")
        if password != confirm_password:
            raise ValidationError("Password and password confirmation do not match")

        # 4. Validate language
        lang = preferred_language.strip().lower() if preferred_language else "en"
        if lang not in ("en", "kn"):
            lang = "en"

        # 5. Check for duplicate account in DB
        db = self._session_factory()
        try:
            existing = db.query(User).filter_by(email=email).first()
            if existing:
                raise ValidationError("An account with this email address already exists")

            # Hash password securely
            pwd_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")

            user = User(
                display_name=display_name,
                email=email,
                phone=phone.strip() if phone else None,
                role="citizen",
                preferred_language=lang,
                password_hash=pwd_hash,
                is_active=True,
            )
            db.add(user)
            db.commit()

            token = generate_auth_token(user.id, user.role)
            return {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
                "phone": user.phone,
                "role": user.role,
                "preferred_language": user.preferred_language,
                "token": token,
            }
        finally:
            db.close()

    def authenticate(
        self, email: str, password: str, client_ip: str = "127.0.0.1"
    ) -> Tuple[Dict[str, Any], str]:
        """
        Authenticates user credentials against rate-limiting rules.
        Returns (user_dict, auth_token).
        """
        if not email or not password:
            raise ValidationError("Email and password are required")

        email_clean = email.strip().lower()
        rate_key = f"{client_ip}:{email_clean}"
        self._check_rate_limit(rate_key)

        db = self._session_factory()
        try:
            user = db.query(User).filter_by(email=email_clean).first()
            if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
                self._record_failed_attempt(rate_key)
                raise ValidationError("Invalid email or password")

            if not user.is_active:
                raise ValidationError("This account has been deactivated. Please contact municipal support.")

            # Clear failure attempts on success
            self._clear_failed_attempts(rate_key)

            # Update last login timestamp
            user.last_login_at = datetime.now(timezone.utc)
            db.commit()

            token = generate_auth_token(user.id, user.role)
            return {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
                "phone": user.phone,
                "role": user.role,
                "preferred_language": user.preferred_language,
            }, token
        finally:
            db.close()

    def get_profile_and_stats(self, user_id: str) -> Dict[str, Any]:
        """Retrieves profile details and real report counts for the user."""
        db = self._session_factory()
        try:
            user = db.query(User).filter_by(id=user_id, is_active=True).first()
            if not user:
                raise NotFoundError("User not found")

            # Compute real statistics from database
            reports = db.query(CitizenReport).filter_by(citizen_id=user_id).all()
            total_reports = len(reports)
            awaiting_review = sum(1 for r in reports if r.status in ("submitted", "pending"))
            under_review = sum(1 for r in reports if r.status == "under_review")
            acknowledged = sum(1 for r in reports if r.status in ("acknowledged", "linked"))
            resolved = sum(1 for r in reports if r.status in ("resolved", "repaired"))

            return {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
                "phone": user.phone,
                "role": user.role,
                "preferred_language": user.preferred_language,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "stats": {
                    "total_reports": total_reports,
                    "awaiting_review": awaiting_review,
                    "under_review": under_review,
                    "acknowledged": acknowledged,
                    "resolved": resolved,
                },
            }
        finally:
            db.close()

    def update_profile(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        phone: Optional[str] = None,
        preferred_language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates permitted citizen profile fields (display name, phone, language)."""
        db = self._session_factory()
        try:
            user = db.query(User).filter_by(id=user_id, is_active=True).first()
            if not user:
                raise NotFoundError("User not found")

            if display_name is not None:
                if len(display_name.strip()) < 2:
                    raise ValidationError("Full name must be at least 2 characters")
                user.display_name = display_name.strip()

            if phone is not None:
                user.phone = phone.strip() if phone.strip() else None

            if preferred_language is not None:
                lang = preferred_language.strip().lower()
                if lang in ("en", "kn"):
                    user.preferred_language = lang

            user.updated_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
                "phone": user.phone,
                "role": user.role,
                "preferred_language": user.preferred_language,
            }
        finally:
            db.close()
