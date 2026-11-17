"""
Assignment Repository
=====================
Persistence operations for municipal incident assignments, inspections, and resolution proofs.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.db.models import IncidentAssignment, WorkProgressUpdate, InspectionRecord, ResolutionRecord


class AssignmentRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_assignment(self, data: Dict[str, Any]) -> IncidentAssignment:
        """Assigns an incident to a department and official."""
        assignment = IncidentAssignment(**data)
        self.session.add(assignment)
        self.session.flush()
        return assignment

    def get_active_assignment(self, incident_id: str) -> Optional[IncidentAssignment]:
        """Retrieves current active assignment for an incident."""
        return (
            self.session.query(IncidentAssignment)
            .filter_by(incident_id=incident_id, is_active=True)
            .order_by(IncidentAssignment.created_at.desc())
            .first()
        )

    def record_progress(self, data: Dict[str, Any]) -> WorkProgressUpdate:
        """Records a repair status progress update."""
        update = WorkProgressUpdate(**data)
        self.session.add(update)
        self.session.flush()
        return update

    def create_inspection(self, data: Dict[str, Any]) -> InspectionRecord:
        """Records an official site inspection."""
        inspection = InspectionRecord(**data)
        self.session.add(inspection)
        self.session.flush()
        return inspection

    def create_resolution(self, data: Dict[str, Any]) -> ResolutionRecord:
        """Records physical completion and repair resolution."""
        resolution = ResolutionRecord(**data)
        self.session.add(resolution)
        self.session.flush()
        return resolution

    def get_assignment_history(self, incident_id: str) -> List[IncidentAssignment]:
        """Retrieves all past and present assignments for an incident."""
        return (
            self.session.query(IncidentAssignment)
            .filter_by(incident_id=incident_id)
            .order_by(IncidentAssignment.created_at.desc())
            .all()
        )
