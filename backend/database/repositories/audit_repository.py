"""
Audit Repository
================
Immutable event logging for security auditing and compliance.
"""

from typing import List, Optional, Dict, Any
import json
import uuid
import time
from sqlalchemy.orm import Session
from backend.db.models import AuditLog


class AuditRepository:
    def __init__(self, session: Session):
        self.session = session

    def log_action(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """Records an immutable audit event."""
        payload = details if isinstance(details, str) else json.dumps(details or {})
        entry = AuditLog(
            id=str(uuid.uuid4()),
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            details=payload,
            created_at=time.time(),
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def get_history(self, entity_type: str, entity_id: str) -> List[AuditLog]:
        """Retrieves audit entries for an entity."""
        return (
            self.session.query(AuditLog)
            .filter_by(entity_type=entity_type, entity_id=entity_id)
            .order_by(AuditLog.created_at.desc())
            .all()
        )
