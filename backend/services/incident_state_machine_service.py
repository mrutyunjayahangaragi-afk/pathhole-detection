"""
Incident State Machine Service
==============================
Enforces canonical incident lifecycle transitions, role-based transition
authorization, audit logging, and citizen report synchronization.
"""

from typing import Optional, Dict, Any, List, Set, Tuple
from datetime import datetime, timezone
import uuid
import json
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, IncidentStatusHistory, CitizenReport, ReportItem,
    CitizenVisibleUpdate, AuditLog, User, DepartmentMembership
)
from backend.errors import ValidationError, NotFoundError, CivicLensError


class IncidentStatus:
    NEW = "new"
    AWAITING_VERIFICATION = "awaiting_verification"
    VERIFIED = "verified"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REJECTED = "rejected"

    ALL: Set[str] = {
        NEW, AWAITING_VERIFICATION, VERIFIED, ASSIGNED,
        IN_PROGRESS, ON_HOLD, RESOLVED, CLOSED, REJECTED
    }


class IncidentStateMachineService:
    """Manages lifecycle transitions for canonical Incident entities."""

    VALID_TRANSITIONS: Dict[str, Set[str]] = {
        IncidentStatus.NEW: {
            IncidentStatus.AWAITING_VERIFICATION,
            IncidentStatus.VERIFIED,
            IncidentStatus.REJECTED
        },
        IncidentStatus.AWAITING_VERIFICATION: {
            IncidentStatus.VERIFIED,
            IncidentStatus.REJECTED,
            IncidentStatus.ON_HOLD
        },
        IncidentStatus.VERIFIED: {
            IncidentStatus.ASSIGNED,
            IncidentStatus.IN_PROGRESS,
            IncidentStatus.ON_HOLD,
            IncidentStatus.REJECTED
        },
        IncidentStatus.ASSIGNED: {
            IncidentStatus.IN_PROGRESS,
            IncidentStatus.ON_HOLD,
            IncidentStatus.REJECTED,
            IncidentStatus.ASSIGNED  # Reassignment in-place
        },
        IncidentStatus.IN_PROGRESS: {
            IncidentStatus.ON_HOLD,
            IncidentStatus.RESOLVED,
            IncidentStatus.ASSIGNED
        },
        IncidentStatus.ON_HOLD: {
            IncidentStatus.IN_PROGRESS,
            IncidentStatus.ASSIGNED,
            IncidentStatus.REJECTED
        },
        IncidentStatus.RESOLVED: {
            IncidentStatus.CLOSED,
            IncidentStatus.IN_PROGRESS  # Reopen if rejected during verification
        },
        IncidentStatus.CLOSED: {
            IncidentStatus.IN_PROGRESS  # Exceptional reopen by municipal_admin
        },
        IncidentStatus.REJECTED: {
            IncidentStatus.AWAITING_VERIFICATION  # Appeal or re-evaluation
        },
    }

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def can_transition(
        self,
        current_status: str,
        new_status: str,
        user_role: str,
        is_assigned_officer: bool = False,
        is_dept_member: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates if a transition from current_status to new_status is permitted
        under the state machine graph and the user's role.
        """
        if new_status not in IncidentStatus.ALL:
            return False, f"Invalid destination status: '{new_status}'"

        # Check graph transition
        allowed = self.VALID_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            return False, f"Cannot transition incident from '{current_status}' to '{new_status}'."

        # Role checks
        if user_role in {"system_admin", "municipal_admin"}:
            return True, None

        if user_role == "dept_admin":
            # Department admin can perform any valid transition except reopening closed
            if current_status == IncidentStatus.CLOSED and new_status == IncidentStatus.IN_PROGRESS:
                return False, "Only municipal admins can reopen closed incidents."
            return True, None

        if user_role == "municipal_officer":
            # Officer can only transition incidents assigned to them
            if not is_assigned_officer and not is_dept_member:
                return False, "Municipal officers can only transition incidents assigned to them or their unit."
            # Officer cannot unilaterally close or reject canonical incidents
            if new_status in {IncidentStatus.CLOSED, IncidentStatus.REJECTED}:
                return False, "Municipal officers cannot close or reject canonical incidents directly. Dept Admin approval required."
            return True, None

        return False, f"Role '{user_role}' has no permission to transition incident status."

    def transition_incident(
        self,
        incident_id: str,
        new_status: str,
        actor_id: str,
        actor_role: str,
        reason: str,
        session: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Executes a canonical status transition, records audit trail, and synchronizes citizen reports.
        """
        if not reason or len(reason.strip()) < 3:
            raise ValidationError("A clear reason (at least 3 characters) is required for every status transition.")

        own_session = session is None
        db: Session = self._session_factory() if own_session else session

        try:
            incident = db.query(Incident).filter_by(id=incident_id).first()
            if not incident:
                raise NotFoundError(f"Incident '{incident_id}' not found.")

            old_status = incident.status or IncidentStatus.NEW

            # Check officer assignment
            is_assigned_officer = (incident.assigned_officer_id == actor_id)

            # Check dept membership
            is_dept_member = False
            if incident.department_id:
                mem = db.query(DepartmentMembership).filter_by(
                    user_id=actor_id,
                    department_id=incident.department_id,
                    is_active=True
                ).first()
                if mem:
                    is_dept_member = True

            can_move, err_msg = self.can_transition(
                current_status=old_status,
                new_status=new_status,
                user_role=actor_role,
                is_assigned_officer=is_assigned_officer,
                is_dept_member=is_dept_member
            )
            if not can_move:
                raise ValidationError(err_msg or "Status transition not permitted.")

            # Update incident status
            incident.status = new_status
            incident.updated_at = datetime.now(timezone.utc)
            if new_status == IncidentStatus.RESOLVED and not incident.resolved_at:
                incident.resolved_at = datetime.now(timezone.utc)

            # Record Status History
            history_entry = IncidentStatusHistory(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                previous_status=old_status,
                new_status=new_status,
                changed_by=actor_id,
                reason=reason.strip(),
                created_at=datetime.now(timezone.utc)
            )
            db.add(history_entry)

            # Record Audit Log
            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=actor_id,
                action="incident_status_transition",
                entity_type="incident",
                entity_id=incident.id,
                details=json.dumps({
                    "old_status": old_status,
                    "new_status": new_status,
                    "reason": reason.strip(),
                    "actor_role": actor_role
                }),
                created_at=datetime.now(timezone.utc)
            )
            db.add(audit)

            # If resolved, synchronize linked citizen reports
            reports_synchronized = 0
            if new_status == IncidentStatus.RESOLVED:
                linked_reports = db.query(CitizenReport).join(
                    ReportItem, ReportItem.report_id == CitizenReport.id
                ).filter(ReportItem.incident_id == incident.id).all()
                for rep in linked_reports:
                    rep.status = "resolved"
                    rep.updated_at = datetime.now(timezone.utc)
                    reports_synchronized += 1

                # Add a CitizenVisibleUpdate notifying citizens
                cit_update = CitizenVisibleUpdate(
                    id=str(uuid.uuid4()),
                    incident_id=incident.id,
                    published_by=actor_id,
                    public_message=f"Incident resolved by municipal maintenance team: {reason.strip()}",
                    status_label="Resolved",
                    created_at=datetime.now(timezone.utc)
                )
                db.add(cit_update)

            elif new_status == IncidentStatus.IN_PROGRESS:
                cit_update = CitizenVisibleUpdate(
                    id=str(uuid.uuid4()),
                    incident_id=incident.id,
                    published_by=actor_id,
                    public_message="Work is currently underway by the municipal engineering department.",
                    status_label="In Progress",
                    created_at=datetime.now(timezone.utc)
                )
                db.add(cit_update)

            if own_session:
                db.commit()

            return {
                "incident_id": incident.id,
                "old_status": old_status,
                "new_status": new_status,
                "reports_synchronized": reports_synchronized,
                "updated_at": incident.updated_at.isoformat()
            }
        except Exception:
            if own_session:
                db.rollback()
            raise
        finally:
            if own_session:
                db.close()
