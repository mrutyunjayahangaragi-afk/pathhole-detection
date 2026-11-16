"""
Official Invitations Management
===============================
Provides invitation lifecycle functions for municipal personnel onboarding.
"""

from typing import Dict, Any, Tuple
from backend.services.official_auth_service import OfficialAuthService

_service = OfficialAuthService()


def create_invitation(
    invited_email: str,
    intended_role: str,
    municipality_id: str,
    invited_by: str,
    department_id: str = None,
    expires_in_days: int = 7
) -> Dict[str, Any]:
    """Issues an official invitation."""
    return _service.create_invitation(
        invited_email=invited_email,
        intended_role=intended_role,
        municipality_id=municipality_id,
        invited_by=invited_by,
        department_id=department_id,
        expires_in_days=expires_in_days,
    )


def verify_invitation(token: str) -> Dict[str, Any]:
    """Verifies validity and role of an invitation token."""
    return _service.verify_invitation(token)


def accept_invitation(
    token: str, display_name: str, password: str, confirm_password: str
) -> Tuple[Dict[str, Any], str]:
    """Consumes an invitation and sets account credentials."""
    return _service.accept_invitation(
        raw_token=token,
        display_name=display_name,
        password=password,
        confirm_password=confirm_password,
    )
