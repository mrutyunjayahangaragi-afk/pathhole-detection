"""
Incident Service
================

Manages canonical Incident lifecycle operations, status progression workflows,
and municipal statistics aggregation.
"""

from typing import List, Dict, Any, Optional
import time
import sqlite3

from backend.database import get_db
from backend.domain.models import Incident, IncidentStatus, SeverityLevel
from backend.errors import NotFoundError, ValidationError


class IncidentService:
    """Encapsulates incident querying, status transitions, and metric aggregation."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def get_incident_by_id(self, incident_id: str) -> Dict[str, Any]:
        """Retrieves a single incident by ID."""
        with get_db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM detections WHERE id = ?", (incident_id,)).fetchone()
            if not row:
                raise NotFoundError(f"Incident with ID '{incident_id}' not found.")
            return dict(row)

    def list_incidents(
        self,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Lists incidents with optional filtering and pagination."""
        if severity and severity not in {"minor", "moderate", "severe"}:
            raise ValidationError(f"Invalid severity filter: '{severity}'")
        if status and status not in {"reported", "acknowledged", "scheduled", "repaired"}:
            raise ValidationError(f"Invalid status filter: '{status}'")

        limit = min(max(1, limit), 1000)
        offset = max(0, offset)

        query = "SELECT * FROM detections WHERE 1=1"
        params = []
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with get_db(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def update_incident_status(self, incident_id: str, new_status_str: str) -> Dict[str, Any]:
        """Updates the municipal status of an incident."""
        allowed_statuses = {"reported", "acknowledged", "scheduled", "repaired"}
        if new_status_str not in allowed_statuses:
            raise ValidationError(f"Status must be one of {sorted(allowed_statuses)}")

        with get_db(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE detections SET status = ? WHERE id = ?", (new_status_str, incident_id)
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"Incident with ID '{incident_id}' not found.")
            
            row = conn.execute("SELECT * FROM detections WHERE id = ?", (incident_id,)).fetchone()
            return dict(row)

    def get_statistics(self) -> Dict[str, Any]:
        """Calculates municipal aggregate metrics."""
        with get_db(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) c FROM detections").fetchone()["c"]
            by_severity = conn.execute(
                "SELECT severity, COUNT(*) c FROM detections WHERE status != 'repaired' GROUP BY severity"
            ).fetchall()
            by_status = conn.execute(
                "SELECT status, COUNT(*) c FROM detections GROUP BY status"
            ).fetchall()
            vehicles = conn.execute(
                "SELECT COUNT(DISTINCT vehicle_id) c FROM detections"
            ).fetchone()["c"]

        return {
            "total_reports": total,
            "active_vehicles": vehicles,
            "open_by_severity": {r["severity"]: r["c"] for r in by_severity},
            "by_status": {r["status"]: r["c"] for r in by_status},
        }
