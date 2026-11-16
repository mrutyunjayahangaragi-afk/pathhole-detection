"""
CivicLens Notification Preference Service
=========================================
Manages citizen and officer notification channel preferences, quiet hours, and opt-outs.
"""

import json
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import NotificationPreference, AuditLog, User

logger = logging.getLogger("civiclens.notif_preferences")


class NotificationPreferenceService:
    """Service managing channel delivery preferences and quiet hours."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def _get_db(self) -> Session:
        return self._session_factory()

    def get_or_create_preferences(self, user_id: str) -> Dict[str, Any]:
        """Retrieves or initializes user notification preferences."""
        db = self._get_db()
        try:
            pref = db.query(NotificationPreference).filter_by(user_id=user_id).first()
            if not pref:
                pref = NotificationPreference(
                    user_id=user_id,
                    in_app_enabled=True,
                    email_enabled=True,
                    sms_enabled=False,
                    whatsapp_enabled=False,
                    push_enabled=False,
                    quiet_hours_enabled=False,
                )
                db.add(pref)
                db.commit()
                db.refresh(pref)

            return self._format_preferences(pref)
        finally:
            db.close()

    def update_preferences(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates specific notification preferences for the user."""
        db = self._get_db()
        try:
            pref = db.query(NotificationPreference).filter_by(user_id=user_id).first()
            if not pref:
                pref = NotificationPreference(user_id=user_id)
                db.add(pref)

            if "in_app_enabled" in updates:
                pref.in_app_enabled = bool(updates["in_app_enabled"])
            if "email_enabled" in updates:
                pref.email_enabled = bool(updates["email_enabled"])
            if "sms_enabled" in updates:
                pref.sms_enabled = bool(updates["sms_enabled"])
            if "whatsapp_enabled" in updates:
                pref.whatsapp_enabled = bool(updates["whatsapp_enabled"])
            if "push_enabled" in updates:
                pref.push_enabled = bool(updates["push_enabled"])
            if "quiet_hours_enabled" in updates:
                pref.quiet_hours_enabled = bool(updates["quiet_hours_enabled"])
            if "quiet_hours_start" in updates:
                pref.quiet_hours_start = str(updates["quiet_hours_start"]) if updates["quiet_hours_start"] else None
            if "quiet_hours_end" in updates:
                pref.quiet_hours_end = str(updates["quiet_hours_end"]) if updates["quiet_hours_end"] else None

            db.flush()

            # Audit log
            audit = AuditLog(
                actor_id=user_id,
                action="UPDATE_NOTIFICATION_PREFERENCES",
                entity_type="NotificationPreference",
                entity_id=pref.id or user_id,
                details=json.dumps({"updated_fields": list(updates.keys())}),
            )
            db.add(audit)
            db.commit()
            db.refresh(pref)

            return self._format_preferences(pref)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _format_preferences(pref: NotificationPreference) -> Dict[str, Any]:
        return {
            "user_id": pref.user_id,
            "in_app_enabled": pref.in_app_enabled,
            "email_enabled": pref.email_enabled,
            "sms_enabled": pref.sms_enabled,
            "whatsapp_enabled": pref.whatsapp_enabled,
            "push_enabled": pref.push_enabled,
            "quiet_hours_enabled": pref.quiet_hours_enabled,
            "quiet_hours_start": pref.quiet_hours_start,
            "quiet_hours_end": pref.quiet_hours_end,
            "updated_at": pref.updated_at.isoformat() if pref.updated_at else None,
        }
