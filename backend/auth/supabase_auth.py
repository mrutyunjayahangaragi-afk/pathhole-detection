"""
Supabase Auth Integration
=========================
Validates Supabase Auth sessions, Google OAuth identities, and maps them
to PostgreSQL User profiles with strict server-side authorization.
"""

from typing import Optional, Dict, Any, Tuple
import requests
from backend.config import get_config
from backend.database.session import get_db_session
from backend.database.repositories.profile_repository import ProfileRepository
from backend.database.repositories.organization_repository import OrganizationRepository
from backend.database.repositories.role_repository import RoleRepository
from backend.services.official_auth_service import OfficialAuthService


class SupabaseAuthService:
    def __init__(self):
        self.config = get_config()

    def verify_supabase_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        Validates an access token with the Supabase Auth server.
        Returns the Supabase user payload or None if invalid/expired.
        """
        if not access_token:
            return None

        supabase_url = getattr(self.config, "SUPABASE_URL", "")
        anon_key = (
            getattr(self.config, "SUPABASE_PUBLISHABLE_KEY", None)
            or getattr(self.config, "SUPABASE_ANON_KEY", "")
        )

        if not supabase_url or not anon_key:
            return None

        endpoint = f"{supabase_url.rstrip('/')}/auth/v1/user"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "apikey": anon_key,
        }

        try:
            resp = requests.get(endpoint, headers=headers, timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception:
            return None

    def authenticate_or_sync_user(
        self,
        supabase_user_data: Dict[str, Any],
        target_portal: str = "citizen"
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Maps a verified Supabase/Google user to a CivicLens profile.
        If target_portal is 'municipal', enforces that an official role or active invitation exists.
        Returns (success: bool, user_dict: dict, error_message: str).
        """
        auth_uid = supabase_user_data.get("id")
        email = supabase_user_data.get("email")
        user_meta = supabase_user_data.get("user_metadata") or {}
        display_name = (
            user_meta.get("full_name")
            or user_meta.get("name")
            or (email.split("@")[0] if email else "Citizen User")
        )

        if not auth_uid or not email:
            return False, None, "Invalid Supabase user payload: missing ID or email"

        session = get_db_session()
        try:
            profile_repo = ProfileRepository(session)
            role_repo = RoleRepository(session)
            org_repo = OrganizationRepository(session)

            # 1. Check if user already exists
            user = profile_repo.get_by_auth_id(auth_uid)
            if not user:
                user = profile_repo.get_by_email(email)

            if target_portal == "municipal":
                # Municipal portal requires official role or active invitation
                if not user or user.role == "citizen":
                    # Check for active official invitation
                    official_auth = OfficialAuthService()
                    invitation = official_auth.get_invitation_by_email(email)
                    if not invitation:
                        return False, None, "Your account does not have authorized municipal access. Please contact your organization's administrator."

            # 2. Sync / create profile safely (defaults to citizen if new)
            user = profile_repo.create_or_sync_google_profile(
                auth_user_id=auth_uid,
                email=email,
                display_name=display_name,
                preferred_language="en",
            )
            session.commit()

            permissions = list(role_repo.get_user_permissions(user))
            memberships = [
                {"department_id": m.department_id, "role": m.official_role}
                for m in org_repo.get_user_memberships(user.id)
            ]

            user_data = {
                "id": user.id,
                "auth_user_id": user.auth_user_id,
                "display_name": user.display_name,
                "email": user.email,
                "role": user.role,
                "preferred_language": user.preferred_language,
                "permissions": permissions,
                "memberships": memberships,
            }
            return True, user_data, None
        except Exception as e:
            session.rollback()
            return False, None, f"Database error during user synchronization: {str(e)}"
        finally:
            session.close()
