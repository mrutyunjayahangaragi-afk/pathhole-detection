"""
CivicLens In-App Notification Service
=====================================
Manages authenticated user notifications inbox, unread counts, and read status updates.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.db.engine import get_session_factory
from backend.db.models import UserNotification

logger = logging.getLogger("civiclens.in_app_notif")


class InAppNotificationService:
    """Service governing in-app notifications inbox and read state transitions."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def _get_db(self) -> Session:
        return self._session_factory()

    def get_user_notifications(
        self,
        user_id: str,
        is_read: Optional[bool] = None,
        category: Optional[str] = None,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Retrieves paginated notifications for the specified user."""
        page = max(1, page)
        limit = min(max(1, limit), 100)
        offset = (page - 1) * limit

        db = self._get_db()
        try:
            query = db.query(UserNotification).filter_by(recipient_id=user_id)

            if is_read is not None:
                query = query.filter_by(is_read=is_read)
            if category and category.lower() != "all":
                query = query.filter_by(category=category.lower().strip())

            total = query.count()
            unread_count = (
                db.query(UserNotification)
                .filter_by(recipient_id=user_id, is_read=False)
                .count()
            )

            notifications = (
                query.order_by(desc(UserNotification.created_at))
                .offset(offset)
                .limit(limit)
                .all()
            )

            items = []
            for n in notifications:
                items.append({
                    "id": n.id,
                    "title": n.title,
                    "message": n.message,
                    "category": n.category,
                    "language": n.language,
                    "is_read": n.is_read,
                    "read_at": n.read_at.isoformat() if n.read_at else None,
                    "related_report_id": n.related_report_id,
                    "related_incident_id": n.related_incident_id,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                })

            return {
                "status": "success",
                "items": items,
                "total": total,
                "unread_count": unread_count,
                "page": page,
                "limit": limit,
            }
        finally:
            db.close()

    def get_unread_count(self, user_id: str) -> int:
        """Returns the total number of unread notifications for a user."""
        db = self._get_db()
        try:
            return (
                db.query(UserNotification)
                .filter_by(recipient_id=user_id, is_read=False)
                .count()
            )
        finally:
            db.close()

    def mark_as_read(self, user_id: str, notification_id: str) -> Dict[str, Any]:
        """Marks a single notification as read with anti-IDOR authorization check."""
        db = self._get_db()
        try:
            notif = (
                db.query(UserNotification)
                .filter_by(id=notification_id, recipient_id=user_id)
                .first()
            )
            if not notif:
                raise PermissionError("Notification not found or access denied.")

            notif.is_read = True
            notif.read_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "status": "success",
                "id": notif.id,
                "is_read": True,
                "read_at": notif.read_at.isoformat(),
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def mark_all_as_read(self, user_id: str) -> Dict[str, Any]:
        """Marks all unread notifications for the user as read."""
        db = self._get_db()
        try:
            now = datetime.now(timezone.utc)
            updated_count = (
                db.query(UserNotification)
                .filter_by(recipient_id=user_id, is_read=False)
                .update({"is_read": True, "read_at": now})
            )
            db.commit()
            return {
                "status": "success",
                "marked_read_count": updated_count,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
