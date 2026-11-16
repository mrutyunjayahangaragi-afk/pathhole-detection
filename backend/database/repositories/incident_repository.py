"""
Incident Repository
===================
Spatial queries, viewport incident retrieval, and department-scoped triage access.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.db.models import Incident, CitizenReport


class IncidentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_public_incidents_in_bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 500
    ) -> List[Incident]:
        """
        Retrieves verified published canonical incidents within a geographic bounding box.
        Excludes rejected or unverified incidents.
        """
        query = self.session.query(Incident).filter(
            Incident.latitude >= min_lat,
            Incident.latitude <= max_lat,
            Incident.longitude >= min_lon,
            Incident.longitude <= max_lon,
            ~Incident.status.in_(["rejected", "closed_unverified"])
        )
        if category:
            query = query.filter(Incident.category == category)
        if severity:
            query = query.filter(Incident.severity == severity)
        return query.order_by(Incident.created_at.desc()).limit(limit).all()

    def get_by_reference(self, reference: str) -> Optional[Incident]:
        """Retrieves an incident by its reference code (e.g. INC-2026-0001)."""
        return self.session.query(Incident).filter_by(incident_reference=reference).first()

    def get_by_id(self, incident_id: str) -> Optional[Incident]:
        """Retrieves an incident by its primary key UUID."""
        return self.session.query(Incident).filter_by(id=incident_id).first()

    def get_department_triage_queue(
        self,
        department_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Incident]:
        """Retrieves incidents for official departmental triage."""
        query = self.session.query(Incident)
        if department_id:
            query = query.filter(Incident.department_id == department_id)
        if status:
            query = query.filter(Incident.status == status)
        return query.order_by(Incident.created_at.desc()).limit(limit).all()
