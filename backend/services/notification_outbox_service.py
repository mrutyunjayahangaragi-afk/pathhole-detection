"""
CivicLens Notification Outbox Service
=====================================
Provides a durable transactional outbox ensuring application state changes
and notification events are committed atomically with zero in-memory event loss.
"""

import json
import logging
import uuid
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import NotificationEvent

logger = logging.getLogger("civiclens.notif_outbox")


class NotificationOutboxService:
    """Transactional outbox manager for durable notification queuing."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def _get_db(self) -> Session:
        return self._session_factory()

    def queue_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        db_session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Durably records an event into notification_events.
        If db_session is provided, executes within the caller's active database transaction.
        """
        if not event_type:
            raise ValueError("event_type is required.")

        key = idempotency_key or f"evt_{event_type}_{uuid.uuid4().hex[:12]}"
        payload_str = json.dumps(payload, default=str)

        should_close = False
        db = db_session
        if db is None:
            db = self._get_db()
            should_close = True

        try:
            # Check idempotency
            existing = db.query(NotificationEvent).filter_by(idempotency_key=key).first()
            if existing:
                return {
                    "id": existing.id,
                    "event_type": existing.event_type,
                    "idempotency_key": existing.idempotency_key,
                    "processing_status": existing.processing_status,
                    "is_duplicate": True,
                }

            event = NotificationEvent(
                event_type=event_type,
                event_payload=payload_str,
                idempotency_key=key,
                processing_status="PENDING",
            )
            db.add(event)
            if should_close:
                db.commit()
                db.refresh(event)

            return {
                "id": event.id,
                "event_type": event.event_type,
                "idempotency_key": event.idempotency_key,
                "processing_status": event.processing_status,
                "is_duplicate": False,
            }
        except Exception:
            if should_close:
                db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    def get_pending_events(self, limit: int = 50) -> List[NotificationEvent]:
        """Retrieves pending outbox events for background worker processing."""
        db = self._get_db()
        try:
            return (
                db.query(NotificationEvent)
                .filter(NotificationEvent.processing_status == "PENDING")
                .order_by(NotificationEvent.created_at.asc())
                .limit(limit)
                .all()
            )
        finally:
            db.close()
