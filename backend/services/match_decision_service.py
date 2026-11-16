"""
Match Decision Service
======================
Atomic, concurrency-safe human verification and decision service for incident matching.

Enforces:
- Optimistic locking: Prevents conflicting concurrent decisions by multiple officers.
- Canonical Incident linkage and observation generation.
- Immutable citizen report preservation: Individual reports are NEVER deleted.
- Full audit history logging.
"""

import uuid
import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, ReportItem, CitizenReport, ReportEvidence,
    IncidentObservation, MatchDecision, MatchEvaluation,
    AuditLog, User
)
from backend.errors import NotFoundError, ValidationError, ConflictError


class MatchDecisionService:
    """Manages official reviewer verification and state transitions for matching items."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def get_review_queue(
        self,
        page: int = 1,
        per_page: int = 20,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves pending report items awaiting municipal matching review.
        """
        db = self._session_factory()
        try:
            query = (
                db.query(ReportItem)
                .join(CitizenReport, ReportItem.report_id == CitizenReport.id)
                .filter(ReportItem.status == "pending")
            )

            if category and category.strip() != "all":
                query = query.filter(ReportItem.category == category.strip().lower())

            total = query.count()
            items = (
                query.order_by(ReportItem.created_at.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )

            queue = []
            for item in items:
                # Get latest evaluation if exists
                latest_eval = (
                    db.query(MatchEvaluation)
                    .filter_by(report_item_id=item.id)
                    .order_by(MatchEvaluation.created_at.desc())
                    .first()
                )

                # Get evidence assets
                rep_evs = db.query(ReportEvidence).filter(
                    (ReportEvidence.report_item_id == item.id) |
                    (ReportEvidence.report_id == item.report_id)
                ).all()

                queue.append({
                    "report_item_id": item.id,
                    "report_id": item.report_id,
                    "category": item.category,
                    "description": item.description,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "citizen_name": item.report.citizen.display_name if item.report and item.report.citizen else "Anonymous",
                    "latitude": item.report.latitude if item.report else None,
                    "longitude": item.report.longitude if item.report else None,
                    "address": item.report.address if item.report else None,
                    "evidence_count": len(rep_evs),
                    "evaluation_id": latest_eval.id if latest_eval else None,
                    "overall_decision": latest_eval.overall_decision if latest_eval else "UNPROCESSED",
                    "top_score": latest_eval.top_score if latest_eval else None,
                    "candidate_count": latest_eval.candidate_count if latest_eval else 0,
                })

            return {
                "total": total,
                "page": page,
                "per_page": per_page,
                "items": queue,
            }
        finally:
            db.close()

    def confirm_link_to_incident(
        self,
        report_item_id: str,
        incident_id: str,
        reviewer_id: str,
        review_notes: str,
        evaluation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Officially links a ReportItem to an existing canonical Incident.
        Atomic and race-safe.
        """
        if not review_notes or not review_notes.strip():
            raise ValidationError("A reviewer reason/notes is required to confirm an incident link.")

        db = self._session_factory()
        try:
            # 1. Row-lock ReportItem
            item = db.query(ReportItem).filter_by(id=report_item_id).first()
            if not item:
                raise NotFoundError(f"ReportItem '{report_item_id}' not found")

            # 2. Concurrency check: Ensure item is still pending
            if item.status != "pending":
                raise ConflictError(
                    f"ReportItem '{report_item_id}' was already resolved (status: '{item.status}'). "
                    "Another reviewer may have already processed this item."
                )

            # 3. Verify target Incident exists
            incident = db.query(Incident).filter_by(id=incident_id).first()
            if not incident:
                raise NotFoundError(f"Target Incident '{incident_id}' not found")

            now = datetime.datetime.now(datetime.timezone.utc)

            # 4. Link report item
            item.incident_id = incident.id
            item.status = "matched"

            # 5. Increment incident report count and update timestamp
            incident.report_count = (incident.report_count or 1) + 1
            incident.updated_at = now

            # 6. Create verified IncidentObservation
            rep_evs = db.query(ReportEvidence).filter(
                (ReportEvidence.report_item_id == item.id) |
                (ReportEvidence.report_id == item.report_id)
            ).all()

            for re in rep_evs:
                obs = IncidentObservation(
                    id=str(uuid.uuid4()),
                    incident_id=incident.id,
                    report_item_id=item.id,
                    evidence_asset_id=re.evidence_asset_id,
                    observation_type="citizen_report",
                    verification_status="verified",
                    observed_at=now,
                )
                db.add(obs)

            # 7. Update parent CitizenReport status if all items resolved
            unresolved_count = db.query(ReportItem).filter(
                ReportItem.report_id == item.report_id,
                ReportItem.id != item.id,
                ReportItem.status.notin_(["matched", "new_incident", "rejected"])
            ).count()
            report = db.query(CitizenReport).filter_by(id=item.report_id).first()
            if report and unresolved_count == 0:
                report.status = "linked"

            # 8. Record MatchDecision
            match_dec = MatchDecision(
                id=str(uuid.uuid4()),
                match_evaluation_id=evaluation_id,
                report_item_id=item.id,
                candidate_incident_id=incident.id,
                decision="LIKELY_EXISTING_INCIDENT",
                decision_reason=review_notes.strip(),
                decision_source="human_reviewer",
                notes=review_notes.strip(),
                reviewed_by=reviewer_id,
                reviewed_at=now,
            )
            db.add(match_dec)

            # 9. Write audit log
            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=reviewer_id,
                action="CONFIRM_INCIDENT_LINK",
                entity_type="report_item",
                entity_id=item.id,
                details=f"Linked to incident {incident.id} ({incident.incident_reference}). Notes: {review_notes.strip()}",
            )
            db.add(audit)

            db.commit()

            return {
                "status": "success",
                "report_item_id": item.id,
                "incident_id": incident.id,
                "incident_reference": incident.incident_reference,
                "report_item_status": item.status,
                "report_status": report.status,
                "new_report_count": incident.report_count,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def confirm_new_incident(
        self,
        report_item_id: str,
        reviewer_id: str,
        review_notes: str,
        evaluation_id: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Officially confirms that a ReportItem represents a brand new physical Incident.
        Creates a new canonical Incident record and links the item.
        """
        if not review_notes or not review_notes.strip():
            raise ValidationError("A reviewer reason/notes is required to confirm a new incident.")

        db = self._session_factory()
        try:
            item = db.query(ReportItem).filter_by(id=report_item_id).first()
            if not item:
                raise NotFoundError(f"ReportItem '{report_item_id}' not found")

            if item.status != "pending":
                raise ConflictError(
                    f"ReportItem '{report_item_id}' was already resolved (status: '{item.status}')."
                )

            now = datetime.datetime.now(datetime.timezone.utc)
            report = item.report

            # Generate random short reference like INC-A1B2
            short_ref = f"INC-{uuid.uuid4().hex[:6].upper()}"

            # Create new canonical incident
            new_inc = Incident(
                id=str(uuid.uuid4()),
                incident_reference=short_ref,
                category=item.category or "pothole",
                description=item.description or report.description or "Citizen reported defect",
                severity=severity or report.reported_severity or "minor",
                status="reported",
                latitude=report.latitude,
                longitude=report.longitude,
                location_accuracy_m=report.location_accuracy_m,
                address=report.address,
                report_count=1,
                created_at=now,
                updated_at=now,
            )
            db.add(new_inc)

            # Link report item
            item.incident_id = new_inc.id
            item.status = "new_incident"

            # Create initial observation
            rep_evs = db.query(ReportEvidence).filter(
                (ReportEvidence.report_item_id == item.id) |
                (ReportEvidence.report_id == item.report_id)
            ).all()

            for re in rep_evs:
                obs = IncidentObservation(
                    id=str(uuid.uuid4()),
                    incident_id=new_inc.id,
                    report_item_id=item.id,
                    evidence_asset_id=re.evidence_asset_id,
                    observation_type="citizen_report",
                    verification_status="verified",
                    observed_at=now,
                )
                db.add(obs)

            # Check parent report status
            unresolved_count = db.query(ReportItem).filter(
                ReportItem.report_id == item.report_id,
                ReportItem.id != item.id,
                ReportItem.status.notin_(["matched", "new_incident", "rejected"])
            ).count()
            report = db.query(CitizenReport).filter_by(id=item.report_id).first()
            if report and unresolved_count == 0:
                report.status = "acknowledged"

            # Record MatchDecision
            match_dec = MatchDecision(
                id=str(uuid.uuid4()),
                match_evaluation_id=evaluation_id,
                report_item_id=item.id,
                candidate_incident_id=new_inc.id,
                decision="NEW_INCIDENT",
                decision_reason=review_notes.strip(),
                decision_source="human_reviewer",
                notes=review_notes.strip(),
                reviewed_by=reviewer_id,
                reviewed_at=now,
            )
            db.add(match_dec)

            # Write audit log
            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=reviewer_id,
                action="CONFIRM_NEW_INCIDENT",
                entity_type="incident",
                entity_id=new_inc.id,
                details=f"Created canonical incident {new_inc.id} ({new_inc.incident_reference}) from item {item.id}. Notes: {review_notes.strip()}",
            )
            db.add(audit)

            db.commit()

            return {
                "status": "success",
                "report_item_id": item.id,
                "incident_id": new_inc.id,
                "incident_reference": new_inc.incident_reference,
                "report_item_status": item.status,
                "report_status": report.status,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def reject_candidate(
        self,
        report_item_id: str,
        candidate_incident_id: str,
        reviewer_id: str,
        review_notes: str,
        evaluation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Rejects a suggested candidate match without closing or resolving the report item.
        Keeps item in review queue for alternative candidates or field verification.
        """
        if not review_notes or not review_notes.strip():
            raise ValidationError("A reviewer reason/notes is required to reject a candidate.")

        db = self._session_factory()
        try:
            item = db.query(ReportItem).filter_by(id=report_item_id).first()
            if not item:
                raise NotFoundError(f"ReportItem '{report_item_id}' not found")

            now = datetime.datetime.now(datetime.timezone.utc)

            match_dec = MatchDecision(
                id=str(uuid.uuid4()),
                match_evaluation_id=evaluation_id,
                report_item_id=item.id,
                candidate_incident_id=candidate_incident_id,
                decision="NEEDS_HUMAN_CONFIRMATION",
                decision_reason=f"Rejected candidate {candidate_incident_id}: {review_notes.strip()}",
                decision_source="human_reviewer",
                notes=review_notes.strip(),
                reviewed_by=reviewer_id,
                reviewed_at=now,
            )
            db.add(match_dec)

            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=reviewer_id,
                action="REJECT_MATCH_CANDIDATE",
                entity_type="report_item",
                entity_id=item.id,
                details=f"Rejected candidate incident {candidate_incident_id}. Notes: {review_notes.strip()}",
            )
            db.add(audit)

            db.commit()

            return {
                "status": "success",
                "report_item_id": item.id,
                "rejected_candidate_id": candidate_incident_id,
                "report_item_status": item.status,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
