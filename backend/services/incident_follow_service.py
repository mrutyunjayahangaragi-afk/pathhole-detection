"""
CivicLens Incident Follow Service
=================================
Allows authenticated citizens to follow and watch approved public incidents
of community interest and manage notification delivery preferences.
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.db.engine import get_session_factory
from backend.db.models import Incident, IncidentFollow, IncidentPublication

logger = logging.getLogger("civiclens.incident_follow")


class IncidentFollowService:
    """Service governing incident following and citizen watchlists."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def _get_db(self) -> Session:
        return self._session_factory()

    def follow_incident(
        self,
        citizen_id: str,
        incident_id: str,
        channels: str = "in_app,email"
    ) -> Dict[str, Any]:
        """
        Follows an approved public incident. Idempotent: returns existing follow if already present.
        """
        if not citizen_id:
            raise ValueError("citizen_id is required to follow an incident.")
        if not incident_id:
            raise ValueError("incident_id is required.")

        db = self._get_db()
        try:
            # Verify incident exists and is approved for public visibility
            inc = (
                db.query(Incident)
                .outerjoin(IncidentPublication, Incident.id == IncidentPublication.incident_id)
                .filter(Incident.id == incident_id)
                .first()
            )
            if not inc:
                raise ValueError("Incident not found.")

            pub = inc.publication
            if pub and pub.visibility_status not in ["PUBLIC", "PENDING_PUBLICATION"]:
                raise PermissionError("Cannot follow private or unapproved incidents.")
            if not pub and inc.status in ["new", "rejected"]:
                raise PermissionError("Cannot follow unverified or rejected incidents.")

            # Check if existing follow
            existing = (
                db.query(IncidentFollow)
                .filter_by(citizen_id=citizen_id, incident_id=incident_id)
                .first()
            )
            if existing:
                existing.notification_channels = channels
                db.commit()
                return {
                    "status": "success",
                    "action": "already_following",
                    "follow_id": existing.id,
                    "incident_id": incident_id,
                    "channels": existing.notification_channels,
                }

            follow = IncidentFollow(
                citizen_id=citizen_id,
                incident_id=incident_id,
                notification_channels=channels,
            )
            db.add(follow)
            db.commit()
            db.refresh(follow)

            return {
                "status": "success",
                "action": "followed",
                "follow_id": follow.id,
                "incident_id": incident_id,
                "channels": follow.notification_channels,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def unfollow_incident(self, citizen_id: str, incident_id: str) -> Dict[str, Any]:
        """Unfollows an incident for the authenticated citizen."""
        db = self._get_db()
        try:
            follow = (
                db.query(IncidentFollow)
                .filter_by(citizen_id=citizen_id, incident_id=incident_id)
                .first()
            )
            if not follow:
                return {
                    "status": "success",
                    "action": "not_following",
                    "incident_id": incident_id,
                }

            db.delete(follow)
            db.commit()
            return {
                "status": "success",
                "action": "unfollowed",
                "incident_id": incident_id,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def is_following(self, citizen_id: str, incident_id: str) -> bool:
        """Checks if the citizen is currently following the specified incident."""
        db = self._get_db()
        try:
            cnt = (
                db.query(IncidentFollow)
                .filter_by(citizen_id=citizen_id, incident_id=incident_id)
                .count()
            )
            return cnt > 0
        finally:
            db.close()

    def get_followed_incidents(
        self, citizen_id: str, page: int = 1, limit: int = 20
    ) -> Dict[str, Any]:
        """Retrieves paginated list of incidents followed by the citizen."""
        page = max(1, page)
        limit = min(max(1, limit), 100)
        offset = (page - 1) * limit

        db = self._get_db()
        try:
            query = (
                db.query(IncidentFollow, Incident)
                .join(Incident, IncidentFollow.incident_id == Incident.id)
                .filter(IncidentFollow.citizen_id == citizen_id)
                .order_by(desc(IncidentFollow.created_at))
            )

            total = query.count()
            rows = query.offset(offset).limit(limit).all()

            results = []
            for follow, inc in rows:
                pub = inc.publication
                results.append({
                    "follow_id": follow.id,
                    "incident_id": inc.id,
                    "incident_reference": inc.incident_reference or f"INC-{inc.id[:8].upper()}",
                    "category": inc.category,
                    "severity": inc.severity,
                    "status": inc.status,
                    "location_name": (pub.public_location_name if pub and pub.public_location_name else inc.address) or "Civic Location",
                    "description": (pub.public_description if pub and pub.public_description else inc.description) or "",
                    "followed_at": follow.created_at.isoformat() if follow.created_at else None,
                    "channels": follow.notification_channels,
                })

            return {
                "status": "success",
                "items": results,
                "total": total,
                "page": page,
                "limit": limit,
            }
        finally:
            db.close()
