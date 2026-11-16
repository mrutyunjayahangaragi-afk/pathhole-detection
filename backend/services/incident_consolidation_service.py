"""
Incident Consolidation Service
==============================
Authorized, human-approved consolidation of two canonical Incident records
that refer to the same physical road defect.

Guarantees:
- Never physically deletes superseded incident records or their history.
- Re-points all associated ReportItems and IncidentObservations to canonical incident.
- Records immutable consolidation audit history in incident_consolidations.
- Increments report counts and preserves all citizen evidence relationships.
"""

import uuid
import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session
from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, ReportItem, IncidentObservation,
    IncidentConsolidation, IncidentStatusHistory, AuditLog
)
from backend.errors import NotFoundError, ValidationError


class IncidentConsolidationService:
    """Manages safe, auditable consolidation of two canonical incident records."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def consolidate_incidents(
        self,
        canonical_incident_id: str,
        superseded_incident_id: str,
        consolidated_by: str,
        consolidation_reason: str,
    ) -> Dict[str, Any]:
        """
        Consolidates superseded_incident into canonical_incident.
        Preserves all reports, observations, and audit histories.
        """
        if canonical_incident_id == superseded_incident_id:
            raise ValidationError("Cannot consolidate an incident into itself. Provide two distinct IDs.")

        if not consolidation_reason or not consolidation_reason.strip():
            raise ValidationError("A clear consolidation reason is required.")

        db = self._session_factory()
        try:
            canonical = db.query(Incident).filter_by(id=canonical_incident_id).first()
            if not canonical:
                raise NotFoundError(f"Canonical incident '{canonical_incident_id}' not found")

            superseded = db.query(Incident).filter_by(id=superseded_incident_id).first()
            if not superseded:
                raise NotFoundError(f"Superseded incident '{superseded_incident_id}' not found")

            now = datetime.datetime.now(datetime.timezone.utc)

            # 1. Re-link ReportItems
            items = db.query(ReportItem).filter_by(incident_id=superseded.id).all()
            for it in items:
                it.incident_id = canonical.id

            # 2. Re-link IncidentObservations
            obs_list = db.query(IncidentObservation).filter_by(incident_id=superseded.id).all()
            for o in obs_list:
                o.incident_id = canonical.id

            # 3. Update report counts
            canonical.report_count = (canonical.report_count or 1) + (superseded.report_count or 1)
            canonical.updated_at = now

            # 4. Update status of superseded incident to closed
            prev_status = superseded.status
            superseded.status = "closed"
            superseded.updated_at = now

            # 5. Record status history for superseded
            stat_hist = IncidentStatusHistory(
                id=str(uuid.uuid4()),
                incident_id=superseded.id,
                previous_status=prev_status,
                new_status="closed",
                changed_by=consolidated_by,
                reason=f"Consolidated into canonical incident {canonical.id} ({canonical.incident_reference}): {consolidation_reason.strip()}",
            )
            db.add(stat_hist)

            # 6. Record consolidation record
            consolidation = IncidentConsolidation(
                id=str(uuid.uuid4()),
                canonical_incident_id=canonical.id,
                superseded_incident_id=superseded.id,
                consolidated_by=consolidated_by,
                consolidation_reason=consolidation_reason.strip(),
                created_at=now,
            )
            db.add(consolidation)

            # 7. Write audit log
            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=consolidated_by,
                action="CONSOLIDATE_INCIDENTS",
                entity_type="incident",
                entity_id=canonical.id,
                details=f"Consolidated superseded incident {superseded.id} into canonical {canonical.id}. Reason: {consolidation_reason.strip()}",
            )
            db.add(audit)

            db.commit()

            return {
                "status": "success",
                "canonical_incident_id": canonical.id,
                "canonical_reference": canonical.incident_reference,
                "superseded_incident_id": superseded.id,
                "superseded_reference": superseded.incident_reference,
                "new_canonical_report_count": canonical.report_count,
                "relinked_items_count": len(items),
                "relinked_observations_count": len(obs_list),
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
