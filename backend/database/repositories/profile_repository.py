"""
Profile Repository
==================
Data access layer for User profiles and Supabase Auth identity mapping.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.db.models import User


class ProfileRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, user_id: str) -> Optional[User]:
        """Retrieves an active user by their internal UUID."""
        return self.session.query(User).filter_by(id=user_id, is_active=True).first()

    def get_by_email(self, email: str) -> Optional[User]:
        """Retrieves an active user by their normalized email address."""
        if not email:
            return None
        return self.session.query(User).filter_by(email=email.strip().lower(), is_active=True).first()

    def get_by_auth_id(self, auth_user_id: str) -> Optional[User]:
        """Retrieves an active user linked to a Supabase Auth identity."""
        if not auth_user_id:
            return None
        return self.session.query(User).filter_by(auth_user_id=auth_user_id, is_active=True).first()

    def create_or_sync_google_profile(
        self,
        auth_user_id: str,
        email: str,
        display_name: str,
        preferred_language: str = "en"
    ) -> User:
        """
        Creates or links a user profile for a verified Google/Supabase Auth identity.
        Default role is ALWAYS 'citizen'. Privileged roles are NEVER granted here.
        """
        norm_email = email.strip().lower() if email else None
        
        # 1. Try finding by auth_user_id first
        user = self.get_by_auth_id(auth_user_id)
        if user:
            user.last_login_at = datetime.now(timezone.utc)
            if display_name and not user.display_name:
                user.display_name = display_name
            self.session.flush()
            return user

        # 2. Try finding by email and link auth_user_id
        if norm_email:
            user = self.get_by_email(norm_email)
            if user:
                user.auth_user_id = auth_user_id
                user.last_login_at = datetime.now(timezone.utc)
                self.session.flush()
                return user

        # 3. Create fresh citizen profile
        user = User(
            auth_user_id=auth_user_id,
            email=norm_email,
            display_name=display_name or (norm_email.split("@")[0] if norm_email else "Citizen User"),
            role="citizen",
            preferred_language=preferred_language or "en",
            is_active=True,
            last_login_at=datetime.now(timezone.utc),
        )
        self.session.add(user)
        self.session.flush()
        return user

    def update_profile(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        phone: Optional[str] = None,
        preferred_language: Optional[str] = None
    ) -> Optional[User]:
        """Updates safe, editable profile attributes."""
        user = self.get_by_id(user_id)
        if not user:
            return None
        if display_name is not None:
            user.display_name = display_name.strip()
        if phone is not None:
            user.phone = phone.strip()
        if preferred_language is not None:
            user.preferred_language = preferred_language.strip().lower()
        self.session.flush()
        return user
