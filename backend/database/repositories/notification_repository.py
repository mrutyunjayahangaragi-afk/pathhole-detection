"""
Notification Repository
=======================
Persistence operations for citizen notification events, in-app alerts, and provider delivery logs.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.db.models import NotificationEvent, UserNotification, NotificationDelivery


class NotificationRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_event(self, data: Dict[str, Any]) -> NotificationEvent:
        """Persists a new transactional notification event."""
        event = NotificationEvent(**data)
        self.session.add(event)
        self.session.flush()
        return event

    def create_user_notification(self, data: Dict[str, Any]) -> UserNotification:
        """Creates an in-app notification for a user."""
        notif = UserNotification(**data)
        self.session.add(notif)
        self.session.flush()
        return notif

    def get_user_notifications(
        self, user_id: str, limit: int = 50
    ) -> List[UserNotification]:
        """Retrieves active notifications for a citizen or official."""
        return (
            self.session.query(UserNotification)
            .filter_by(user_id=user_id)
            .order_by(UserNotification.created_at.desc())
            .limit(limit)
            .all()
        )

    def mark_as_read(self, notification_id: str) -> bool:
        """Marks a notification as read."""
        notif = self.session.query(UserNotification).filter_by(id=notification_id).first()
        if notif:
            notif.is_read = True
            self.session.flush()
            return True
        return False

    def log_delivery(self, data: Dict[str, Any]) -> NotificationDelivery:
        """Records an external channel (Email/SMS/Push) delivery attempt."""
        delivery = NotificationDelivery(**data)
        self.session.add(delivery)
        self.session.flush()
        return delivery
