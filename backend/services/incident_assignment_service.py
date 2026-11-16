"""
CivicLens Incident Assignment Service
=====================================
Manages canonical incident assignments to departments and officers,
enforces department membership matching, requires mandatory audit reasons
for reassignments, and tracks comprehensive assignment history.
"""

from typing import List, Dict, Any, Optional
import uuid
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, Department, DepartmentMembership, User,
    IncidentAssignment, AuditLog, IncidentStatusHistory
)
from backend.services.incident_state_machine_service import IncidentStatus, IncidentStateMachineService
from backend.errors import ValidationError, NotFoundError, CivicLensError


VALID_PRIORITIES = {"low", "normal", "high", "critical"}


class IncidentAssignmentService:
    """Handles departmental routing, officer assignment, and reassignment audits."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory
        self.state_machine = IncidentStateMachineService(session_factory=self._session_factory)

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def assign_department(
        self,
        incident_id: str,
        department_id: str,
        assigned_by: str,
        actor_role: str,
        reason: Optional[str] = None,
        priority: Optional[str] = None
    ) -> Dict[str, Any]:
        """Assigns or transfers a canonical incident to a municipal department."""
        db: Session = self._session_factory()
        try:
            incident = db.query(Incident).filter_by(id=incident_id).first()
            if not incident:
                raise NotFoundError(f"Incident '{incident_id}' not found.")

            dept = db.query(Department).filter_by(id=department_id, is_active=True).first()
            if not dept:
                raise NotFoundError(f"Active department '{department_id}' not found.")

            if priority:
                if priority not in VALID_PRIORITIES:
                    raise ValidationError(f"Invalid priority '{priority}'. Allowed: {sorted(VALID_PRIORITIES)}")
                incident.priority = priority

            old_dept_id = incident.department_id
            incident.department_id = dept.id
            incident.updated_at = datetime.now(timezone.utc)

            # If incident is verified or new, transition to assigned
            old_status = incident.status
            if old_status in {IncidentStatus.NEW, IncidentStatus.AWAITING_VERIFICATION, IncidentStatus.VERIFIED}:
                incident.status = IncidentStatus.ASSIGNED
                history_entry = IncidentStatusHistory(
                    id=str(uuid.uuid4()),
                    incident_id=incident.id,
                    previous_status=old_status,
                    new_status=IncidentStatus.ASSIGNED,
                    changed_by=assigned_by,
                    reason=f"Assigned to {dept.name}: {reason or 'Initial department assignment'}",
                    created_at=datetime.now(timezone.utc)
                )
                db.add(history_entry)

            # Record assignment
            assignment_record = IncidentAssignment(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                department_id=dept.id,
                assigned_to=incident.assigned_officer_id,
                notes=reason.strip() if reason else f"Assigned to department {dept.name}",
                priority=incident.priority,
                assigned_at=datetime.now(timezone.utc)
            )
            db.add(assignment_record)

            # Audit
            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=assigned_by,
                action="assign_department",
                entity_type="incident",
                entity_id=incident.id,
                details=json.dumps({
                    "old_department_id": old_dept_id,
                    "new_department_id": dept.id,
                    "department_code": dept.code,
                    "priority": incident.priority,
                    "reason": reason
                }),
                created_at=datetime.now(timezone.utc)
            )
            db.add(audit)

            db.commit()
            return {
                "incident_id": incident.id,
                "department_id": dept.id,
                "department_name": dept.name,
                "status": incident.status,
                "priority": incident.priority,
                "assigned_at": assignment_record.assigned_at.isoformat()
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def assign_officer(
        self,
        incident_id: str,
        officer_id: str,
        assigned_by: str,
        actor_role: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Assigns or reassigns an incident to an individual officer with mandatory reason for reassignment."""
        db: Session = self._session_factory()
        try:
            incident = db.query(Incident).filter_by(id=incident_id).first()
            if not incident:
                raise NotFoundError(f"Incident '{incident_id}' not found.")

            officer = db.query(User).filter_by(id=officer_id, is_active=True).first()
            if not officer or officer.role not in {"municipal_officer", "dept_admin", "municipal_admin"}:
                raise ValidationError("Target assignee must be an active municipal officer or administrator.")

            # Validate department membership unless municipal_admin
            if actor_role != "municipal_admin" and actor_role != "system_admin" and incident.department_id:
                mem = db.query(DepartmentMembership).filter_by(
                    user_id=officer.id,
                    department_id=incident.department_id,
                    is_active=True
                ).first()
                if not mem:
                    raise ValidationError(
                        f"Officer '{officer.display_name}' is not an active member of the assigned department."
                    )

            # Reassignment guard: if already assigned to a different officer, require clear reason
            old_officer_id = incident.assigned_officer_id
            if old_officer_id and old_officer_id != officer_id:
                if not reason or len(reason.strip()) < 5:
                    raise ValidationError("A clear reason (at least 5 characters) is required when reassigning an incident to another officer.")

            incident.assigned_officer_id = officer.id
            if incident.status in {IncidentStatus.NEW, IncidentStatus.AWAITING_VERIFICATION, IncidentStatus.VERIFIED}:
                incident.status = IncidentStatus.ASSIGNED

            incident.updated_at = datetime.now(timezone.utc)

            assignment_record = IncidentAssignment(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                department_id=incident.department_id,
                assigned_to=officer.id,
                notes=reason.strip() if reason else f"Assigned to officer {officer.display_name}",
                priority=incident.priority,
                assigned_at=datetime.now(timezone.utc)
            )
            db.add(assignment_record)

            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=assigned_by,
                action="assign_officer",
                entity_type="incident",
                entity_id=incident.id,
                details=json.dumps({
                    "old_officer_id": old_officer_id,
                    "new_officer_id": officer.id,
                    "officer_name": officer.display_name,
                    "reason": reason
                }),
                created_at=datetime.now(timezone.utc)
            )
            db.add(audit)

            db.commit()
            return {
                "incident_id": incident.id,
                "assigned_officer_id": officer.id,
                "assigned_officer_name": officer.display_name,
                "department_id": incident.department_id,
                "status": incident.status,
                "assigned_at": assignment_record.assigned_at.isoformat()
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_assignment_history(self, incident_id: str) -> List[Dict[str, Any]]:
        """Retrieves chronological audit trail of all assignments for an incident."""
        db: Session = self._session_factory()
        try:
            records = db.query(IncidentAssignment).filter_by(
                incident_id=incident_id
            ).order_by(IncidentAssignment.assigned_at.asc()).all()

            results = []
            for r in records:
                dept_name = None
                if r.department_id:
                    dept = db.query(Department).filter_by(id=r.department_id).first()
                    dept_name = dept.name if dept else None

                officer_name = None
                if r.assigned_to:
                    u = db.query(User).filter_by(id=r.assigned_to).first()
                    officer_name = u.display_name if u else None

                results.append({
                    "id": r.id,
                    "department_id": r.department_id,
                    "department_name": dept_name,
                    "assigned_officer_id": r.assigned_to,
                    "assigned_officer_name": officer_name,
                    "assignment_reason": r.notes,
                    "priority": r.priority,
                    "assigned_at": r.assigned_at.isoformat() if r.assigned_at else None
                })
            return results
        finally:
            db.close()
