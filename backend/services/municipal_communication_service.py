"""
CivicLens Municipal Communication Service
=========================================
Strictly isolates municipal internal notes from citizen-visible updates.
Protects sensitive operational deliberations, inter-departmental memos,
and administrative comments from public exposure while publishing approved status updates.
"""

from typing import List, Dict, Any, Optional
import uuid
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, MunicipalInternalNote, CitizenVisibleUpdate, User, AuditLog
)
from backend.errors import ValidationError, NotFoundError, CivicLensError


VALID_AUDIENCES = {"internal_officers", "dept_admin_only", "municipal_all"}


class MunicipalCommunicationService:
    """Provides internal municipal collaboration and public citizen communications."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def add_internal_note(
        self,
        incident_id: str,
        author_id: str,
        content: str,
        audience: str = "internal_officers"
    ) -> Dict[str, Any]:
        """Adds an internal note visible ONLY to authorized municipal personnel."""
        if not content or len(content.strip()) < 3:
            raise ValidationError("Note content must be at least 3 characters.")

        if audience not in VALID_AUDIENCES:
            raise ValidationError(f"Invalid note audience '{audience}'. Allowed: {sorted(VALID_AUDIENCES)}")

        db: Session = self._session_factory()
        try:
            incident = db.query(Incident).filter_by(id=incident_id).first()
            if not incident:
                raise NotFoundError(f"Incident '{incident_id}' not found.")

            author = db.query(User).filter_by(id=author_id).first()
            if not author:
                raise NotFoundError(f"User '{author_id}' not found.")

            note = MunicipalInternalNote(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                author_id=author.id,
                content=content.strip(),
                audience=audience,
                created_at=datetime.now(timezone.utc)
            )
            db.add(note)

            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=author_id,
                action="add_internal_note",
                entity_type="incident",
                entity_id=incident.id,
                details=json.dumps({"audience": audience, "content_len": len(note.content)}),
                created_at=datetime.now(timezone.utc)
            )
            db.add(audit)

            db.commit()
            return {
                "id": note.id,
                "incident_id": note.incident_id,
                "author_id": note.author_id,
                "author_name": author.display_name,
                "audience": note.audience,
                "content": note.content,
                "created_at": note.created_at.isoformat()
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_internal_notes(
        self,
        incident_id: str,
        viewer_role: str
    ) -> List[Dict[str, Any]]:
        """Lists internal notes respecting role-based visibility rules."""
        db: Session = self._session_factory()
        try:
            notes = db.query(MunicipalInternalNote).filter_by(
                incident_id=incident_id
            ).order_by(MunicipalInternalNote.created_at.asc()).all()

            results = []
            for n in notes:
                # Visibility rules
                if n.audience == "dept_admin_only" and viewer_role not in {"dept_admin", "municipal_admin", "system_admin"}:
                    continue

                author_name = "Municipal Staff"
                if n.author_id:
                    u = db.query(User).filter_by(id=n.author_id).first()
                    if u:
                        author_name = u.display_name

                results.append({
                    "id": n.id,
                    "author_id": n.author_id,
                    "author_name": author_name,
                    "content": n.content,
                    "audience": n.audience,
                    "created_at": n.created_at.isoformat() if n.created_at else None
                })
            return results
        finally:
            db.close()

    def publish_citizen_update(
        self,
        incident_id: str,
        published_by: str,
        public_message: str,
        status_label: str
    ) -> Dict[str, Any]:
        """Publishes an official citizen-facing update that appears on public tracking."""
        if not public_message or len(public_message.strip()) < 5:
            raise ValidationError("Public message must be at least 5 characters.")

        if not status_label or len(status_label.strip()) < 2:
            raise ValidationError("Status label is required.")

        db: Session = self._session_factory()
        try:
            incident = db.query(Incident).filter_by(id=incident_id).first()
            if not incident:
                raise NotFoundError(f"Incident '{incident_id}' not found.")

            update = CitizenVisibleUpdate(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                published_by=published_by,
                public_message=public_message.strip(),
                status_label=status_label.strip(),
                created_at=datetime.now(timezone.utc)
            )
            db.add(update)

            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=published_by,
                action="publish_citizen_update",
                entity_type="incident",
                entity_id=incident.id,
                details=json.dumps({"status_label": status_label, "message_len": len(public_message)}),
                created_at=datetime.now(timezone.utc)
            )
            db.add(audit)

            db.commit()
            return {
                "id": update.id,
                "incident_id": update.incident_id,
                "published_by": update.published_by,
                "public_message": update.public_message,
                "status_label": update.status_label,
                "created_at": update.created_at.isoformat()
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_citizen_updates(self, incident_id: str) -> List[Dict[str, Any]]:
        """Retrieves all public citizen updates for an incident."""
        db: Session = self._session_factory()
        try:
            updates = db.query(CitizenVisibleUpdate).filter_by(
                incident_id=incident_id
            ).order_by(CitizenVisibleUpdate.created_at.asc()).all()

            results = []
            for u in updates:
                publisher_name = "Civic Maintenance Operations"
                if u.published_by:
                    pub = db.query(User).filter_by(id=u.published_by).first()
                    if pub:
                        publisher_name = pub.display_name

                results.append({
                    "id": u.id,
                    "published_by": u.published_by,
                    "publisher_name": publisher_name,
                    "public_message": u.public_message,
                    "status_label": u.status_label,
                    "created_at": u.created_at.isoformat() if u.created_at else None
                })
            return results
        finally:
            db.close()
