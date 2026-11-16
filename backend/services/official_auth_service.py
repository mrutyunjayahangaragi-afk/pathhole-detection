"""
CivicLens Official & Municipal Authentication & Invitation Service
==================================================================
Handles invitation-based municipal officer and administrator onboarding,
cryptographic token hashing, role verification, and municipal login workflows.
Guarantees that public users cannot self-assign privileged roles.
"""

import hashlib
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List
from werkzeug.security import generate_password_hash, check_password_hash

from backend.db.engine import get_session_factory
from backend.db.models import User, Municipality, Department, DepartmentMembership, OfficialInvitation
from backend.auth import generate_auth_token
from backend.errors import ValidationError, NotFoundError, UnauthorizedError, CivicLensError

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@(?:[\w\-]+\.)+[a-zA-Z]{2,}$")
MUNICIPAL_ROLES = {"municipal_officer", "dept_admin", "municipal_admin", "system_admin"}


class OfficialAuthService:
    """Provides official login verification, invitation creation, and role enforcement."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """Computes SHA-256 hash of an invitation token."""
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def authenticate_official(
        self, email: str, password: str, client_ip: str = "127.0.0.1"
    ) -> Tuple[Dict[str, Any], str]:
        """
        Authenticates municipal official credentials with strict role validation.
        Rejects citizens trying to use the official login portal with an informative error.
        """
        if not email or not password:
            raise ValidationError("Email and password are required.")

        email_clean = email.strip().lower()
        db = self._session_factory()
        try:
            user = db.query(User).filter_by(email=email_clean).first()
            if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
                raise ValidationError("Invalid official email or password.")

            if not user.is_active:
                raise ValidationError("Your official account has been deactivated. Please contact your administrator.")

            if user.role not in MUNICIPAL_ROLES:
                raise UnauthorizedError(
                    "Your account does not have authorized municipal access. "
                    "Official accounts are provisioned via administrative invitation."
                )

            # Retrieve department memberships
            dept_memberships = db.query(DepartmentMembership).filter_by(
                user_id=user.id, is_active=True
            ).all()

            memberships_data = []
            for dm in dept_memberships:
                dept = db.query(Department).filter_by(id=dm.department_id).first()
                memberships_data.append({
                    "department_id": dm.department_id,
                    "department_name": dept.name if dept else "General Department",
                    "role_in_dept": dm.role_in_dept
                })

            user.last_login_at = datetime.now(timezone.utc)
            db.commit()

            token = generate_auth_token(user.id, user.role)
            user_data = {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
                "role": user.role,
                "preferred_language": user.preferred_language,
                "departments": memberships_data
            }
            return user_data, token
        finally:
            db.close()

    def create_invitation(
        self,
        invited_by: User,
        email: str,
        intended_role: str,
        municipality_id: Optional[str] = None,
        department_id: Optional[str] = None,
        expires_in_days: int = 7
    ) -> Dict[str, Any]:
        """
        Creates a time-limited invitation for a new official.
        Enforces hierarchical permissions:
        - system_admin can invite municipal_admin, dept_admin, municipal_officer
        - municipal_admin can invite dept_admin, municipal_officer
        - dept_admin can invite municipal_officer
        """
        if invited_by.role not in {"system_admin", "municipal_admin", "dept_admin"}:
            raise UnauthorizedError("You do not have permission to invite official personnel.")

        if intended_role not in MUNICIPAL_ROLES:
            raise ValidationError(f"Invalid official role '{intended_role}'.")

        # Hierarchy validation
        if invited_by.role == "dept_admin" and intended_role != "municipal_officer":
            raise UnauthorizedError("Department Administrators can only invite Municipal Officers.")
        if invited_by.role == "municipal_admin" and intended_role == "system_admin":
            raise UnauthorizedError("Municipal Administrators cannot provision System Administrators.")

        email_clean = email.strip().lower()
        if not EMAIL_REGEX.match(email_clean):
            raise ValidationError("A valid official email address is required.")

        db = self._session_factory()
        try:
            # Check if active official account already exists
            existing_user = db.query(User).filter_by(email=email_clean, is_active=True).first()
            if existing_user and existing_user.role in MUNICIPAL_ROLES:
                raise ValidationError(f"User '{email_clean}' already holds an active official account.")

            # Generate high-entropy raw token
            raw_token = secrets.token_urlsafe(32)
            token_hash = self.hash_token(raw_token)

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(days=expires_in_days)

            # Invalidate any pending invitations for this email
            db.query(OfficialInvitation).filter_by(
                invited_email=email_clean, status="PENDING"
            ).update({"status": "REVOKED", "revoked_at": now})

            invitation = OfficialInvitation(
                invited_email=email_clean,
                intended_role=intended_role,
                municipality_id=municipality_id,
                department_id=department_id,
                token_hash=token_hash,
                invited_by_id=invited_by.id,
                expires_at=expires_at,
                status="PENDING",
                created_at=now,
                updated_at=now
            )
            db.add(invitation)
            db.commit()

            return {
                "id": invitation.id,
                "invited_email": invitation.invited_email,
                "intended_role": invitation.intended_role,
                "municipality_id": invitation.municipality_id,
                "department_id": invitation.department_id,
                "expires_at": invitation.expires_at.isoformat(),
                "status": invitation.status,
                "invitation_token": raw_token,
                "invitation_url": f"/frontend/municipal/login.html?invitation={raw_token}"
            }
        finally:
            db.close()

    def verify_invitation(self, raw_token: str) -> Dict[str, Any]:
        """Validates an invitation token without consuming it."""
        if not raw_token:
            raise ValidationError("Invitation token is required.")

        token_hash = self.hash_token(raw_token)
        db = self._session_factory()
        try:
            inv = db.query(OfficialInvitation).filter_by(
                token_hash=token_hash, status="PENDING"
            ).first()

            if not inv:
                raise NotFoundError("Invalid or expired invitation token.")

            now = datetime.now(timezone.utc)
            exp = inv.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)

            if now > exp:
                inv.status = "EXPIRED"
                db.commit()
                raise ValidationError("This invitation token has expired. Please request a new invitation.")

            dept_name = None
            if inv.department_id:
                dept = db.query(Department).filter_by(id=inv.department_id).first()
                if dept:
                    dept_name = dept.name

            return {
                "valid": True,
                "email": inv.invited_email,
                "intended_role": inv.intended_role,
                "department_name": dept_name,
                "expires_at": inv.expires_at.isoformat()
            }
        finally:
            db.close()

    def accept_invitation(
        self, raw_token: str, display_name: str, password: str, confirm_password: str
    ) -> Tuple[Dict[str, Any], str]:
        """Consumes the invitation, creates/updates the official account, and returns session token."""
        if not raw_token:
            raise ValidationError("Invitation token is required.")

        if not display_name or len(display_name.strip()) < 2:
            raise ValidationError("Full name must be at least 2 characters.")

        if not password or len(password) < 8:
            raise ValidationError("Password must be at least 8 characters long.")

        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise ValidationError("Password must contain at least one letter and one number.")

        if password != confirm_password:
            raise ValidationError("Passwords do not match.")

        token_hash = self.hash_token(raw_token)
        db = self._session_factory()
        try:
            inv = db.query(OfficialInvitation).filter_by(
                token_hash=token_hash, status="PENDING"
            ).first()

            if not inv:
                raise NotFoundError("Invalid or expired invitation token.")

            now = datetime.now(timezone.utc)
            exp = inv.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)

            if now > exp:
                inv.status = "EXPIRED"
                db.commit()
                raise ValidationError("This invitation token has expired.")

            pwd_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")

            # Check if user already exists
            user = db.query(User).filter_by(email=inv.invited_email).first()
            if user:
                user.display_name = display_name.strip()
                user.password_hash = pwd_hash
                user.role = inv.intended_role
                user.is_active = True
                user.updated_at = now
            else:
                user = User(
                    display_name=display_name.strip(),
                    email=inv.invited_email,
                    role=inv.intended_role,
                    preferred_language="en",
                    password_hash=pwd_hash,
                    is_active=True,
                    created_at=now,
                    updated_at=now
                )
                db.add(user)
                db.flush()

            # Assign Department Membership if invitation specifies department
            if inv.department_id:
                existing_member = db.query(DepartmentMembership).filter_by(
                    user_id=user.id, department_id=inv.department_id
                ).first()
                if not existing_member:
                    role_in_dept = "admin" if inv.intended_role == "dept_admin" else "officer"
                    membership = DepartmentMembership(
                        user_id=user.id,
                        department_id=inv.department_id,
                        role_in_dept=role_in_dept,
                        is_active=True,
                        joined_at=now
                    )
                    db.add(membership)

            inv.status = "ACCEPTED"
            inv.accepted_at = now
            db.commit()

            token = generate_auth_token(user.id, user.role)
            return {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
                "role": user.role
            }, token
        finally:
            db.close()
