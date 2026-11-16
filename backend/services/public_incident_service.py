"""
CivicLens Public Incident & Geospatial Service
=============================================
Manages public incident visibility, spatial viewport queries, canonical projection,
privacy redaction, and marker clustering for the transparent public map.
"""

import json
import logging
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, IncidentPublication, CitizenVisibleUpdate,
    ResolutionRecord, EvidenceAsset, AuditLog, User
)

logger = logging.getLogger("civiclens.public_incident")


class PublicIncidentService:
    """Service governing public-safe incident projections and geospatial querying."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def _get_db(self) -> Session:
        return self._session_factory()

    @staticmethod
    def _sanitize_public_text(text: Optional[str]) -> str:
        """Sanitizes text by stripping whitespace and ensuring safe string fallback."""
        if not text:
            return ""
        return str(text).strip()

    @staticmethod
    def _obfuscate_coords(lat: float, lon: float, precision: int = 3) -> Tuple[float, float]:
        """
        Rounds coordinates to specified decimal places (~100m accuracy at 3 decimals)
        to protect private citizen locations while preserving street-level public map utility.
        """
        return round(float(lat), precision), round(float(lon), precision)

    def get_public_incidents_in_viewport(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        category: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves publicly approved canonical incidents within the given bounding box.
        Enforces public visibility policy and projects only privacy-safe attributes.
        """
        # Validate coordinate boundaries
        if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
            raise ValueError("Latitude must be between -90 and 90 degrees.")
        if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
            raise ValueError("Longitude must be between -180 and 180 degrees.")
        if min_lat > max_lat or min_lon > max_lon:
            raise ValueError("min coordinates cannot be greater than max coordinates.")

        capped_limit = min(max(1, limit), 1000)

        db = self._get_db()
        try:
            # Query incidents within bounding box
            query = (
                db.query(Incident)
                .outerjoin(IncidentPublication, Incident.id == IncidentPublication.incident_id)
                .filter(
                    Incident.latitude >= min_lat,
                    Incident.latitude <= max_lat,
                    Incident.longitude >= min_lon,
                    Incident.longitude <= max_lon,
                )
            )

            # Public Visibility Policy:
            # 1. If explicit IncidentPublication exists: visibility_status must be 'PUBLIC'.
            # 2. If no publication record exists: status must be verified/in-progress/resolved/closed (never new, awaiting_verification, or rejected).
            query = query.filter(
                or_(
                    IncidentPublication.visibility_status == "PUBLIC",
                    and_(
                        IncidentPublication.id == None,
                        Incident.status.in_(["verified", "assigned", "in_progress", "on_hold", "resolved", "closed"])
                    )
                )
            )
            # Never show HIDDEN, PRIVATE, ARCHIVED, or rejected incidents
            query = query.filter(
                or_(
                    IncidentPublication.visibility_status != "HIDDEN",
                    IncidentPublication.id == None
                ),
                or_(
                    IncidentPublication.visibility_status != "PRIVATE",
                    IncidentPublication.id == None
                ),
                or_(
                    IncidentPublication.visibility_status != "ARCHIVED",
                    IncidentPublication.id == None
                ),
                Incident.status != "rejected"
            )

            if category and category.lower() != "all":
                query = query.filter(Incident.category == category.lower().strip())
            if status and status.lower() != "all":
                query = query.filter(Incident.status == status.lower().strip())
            if severity and severity.lower() != "all":
                query = query.filter(Incident.severity == severity.lower().strip())

            incidents = query.order_by(Incident.created_at.desc()).limit(capped_limit).all()

            results = []
            for inc in incidents:
                results.append(self._format_public_incident_summary(inc))

            return results
        finally:
            db.close()

    def get_public_incident_detail(self, ref_or_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves detailed public-safe incident record by canonical reference or UUID.
        Returns None if record does not exist or fails public visibility policy.
        """
        db = self._get_db()
        try:
            inc = (
                db.query(Incident)
                .outerjoin(IncidentPublication, Incident.id == IncidentPublication.incident_id)
                .filter(
                    or_(
                        Incident.incident_reference == ref_or_id.strip(),
                        Incident.id == ref_or_id.strip(),
                    )
                )
                .first()
            )
            if not inc:
                return None

            # Verify public visibility
            pub = inc.publication
            if pub:
                if pub.visibility_status != "PUBLIC":
                    return None
            else:
                if inc.status in ["new", "awaiting_verification", "rejected"]:
                    return None

            return self._format_public_incident_detail(db, inc)
        finally:
            db.close()

    def set_incident_publication(
        self,
        incident_id: str,
        officer_id: Optional[str],
        visibility_status: str,
        public_title: Optional[str] = None,
        public_description: Optional[str] = None,
        public_location_name: Optional[str] = None,
        visibility_reason: Optional[str] = None,
        approved_evidence_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Updates or creates a publication record for an incident."""
        valid_statuses = ("PRIVATE", "PENDING_PUBLICATION", "PUBLIC", "HIDDEN", "ARCHIVED")
        if visibility_status not in valid_statuses:
            raise ValueError(f"Invalid visibility_status '{visibility_status}'. Must be one of {valid_statuses}")

        db = self._get_db()
        try:
            inc = db.query(Incident).filter_by(id=incident_id).first()
            if not inc:
                raise ValueError(f"Incident with ID '{incident_id}' not found.")

            pub = db.query(IncidentPublication).filter_by(incident_id=incident_id).first()
            if not pub:
                pub = IncidentPublication(
                    incident_id=incident_id,
                    visibility_status=visibility_status,
                    published_by=officer_id,
                    public_title=public_title or f"{inc.category.replace('_', ' ').capitalize()} at {inc.address or 'Location'}",
                    public_description=public_description or inc.description,
                    public_location_name=public_location_name or inc.address,
                    public_latitude=inc.latitude,
                    public_longitude=inc.longitude,
                    visibility_reason=visibility_reason,
                    approved_evidence_ids=json.dumps(approved_evidence_ids or []),
                    published_at=datetime.now(timezone.utc) if visibility_status == "PUBLIC" else None,
                )
                db.add(pub)
            else:
                pub.visibility_status = visibility_status
                if officer_id:
                    pub.published_by = officer_id
                if public_title is not None:
                    pub.public_title = public_title
                if public_description is not None:
                    pub.public_description = public_description
                if public_location_name is not None:
                    pub.public_location_name = public_location_name
                if visibility_reason is not None:
                    pub.visibility_reason = visibility_reason
                if approved_evidence_ids is not None:
                    pub.approved_evidence_ids = json.dumps(approved_evidence_ids)
                if visibility_status == "PUBLIC" and not pub.published_at:
                    pub.published_at = datetime.now(timezone.utc)

            # Audit Log
            audit = AuditLog(
                actor_id=officer_id,
                action="UPDATE_PUBLICATION_STATUS",
                entity_type="IncidentPublication",
                entity_id=pub.id,
                details=json.dumps({
                    "incident_id": incident_id,
                    "visibility_status": visibility_status,
                    "reason": visibility_reason or "",
                }),
            )
            db.add(audit)
            db.commit()
            db.refresh(pub)
            return {
                "id": pub.id,
                "incident_id": pub.incident_id,
                "visibility_status": pub.visibility_status,
                "published_at": pub.published_at.isoformat() if pub.published_at else None,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_clustered_incidents(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        grid_size_degrees: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """
        Aggregates incidents into spatial grid cells for efficient zoomed-out visualization.
        Preserves individual incident identity while reducing response payload.
        """
        incidents = self.get_public_incidents_in_viewport(
            min_lon=min_lon, min_lat=min_lat, max_lon=max_lon, max_lat=max_lat, limit=1000
        )

        grid: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for inc in incidents:
            cell_x = int(math.floor(inc["longitude"] / grid_size_degrees))
            cell_y = int(math.floor(inc["latitude"] / grid_size_degrees))
            grid.setdefault((cell_x, cell_y), []).append(inc)

        clusters = []
        for (cx, cy), items in grid.items():
            count = len(items)
            avg_lat = sum(it["latitude"] for it in items) / count
            avg_lon = sum(it["longitude"] for it in items) / count
            severities = [it["severity"] for it in items]
            dominant_severity = max(set(severities), key=severities.count)

            clusters.append({
                "cluster_id": f"cell_{cx}_{cy}",
                "latitude": round(avg_lat, 5),
                "longitude": round(avg_lon, 5),
                "count": count,
                "dominant_severity": dominant_severity,
                "incident_references": [it["incident_reference"] for it in items[:5]],
            })

        return clusters

    def _format_public_incident_summary(self, inc: Incident) -> Dict[str, Any]:
        """Formats incident for public map markers (zero citizen PII)."""
        pub = inc.publication
        safe_lat, safe_lon = self._obfuscate_coords(
            pub.public_latitude if pub and pub.public_latitude else inc.latitude,
            pub.public_longitude if pub and pub.public_longitude else inc.longitude,
        )
        safe_location = (pub.public_location_name if pub and pub.public_location_name else inc.address) or "Civic Location"
        safe_desc = (pub.public_description if pub and pub.public_description else inc.description) or ""

        return {
            "id": inc.id,
            "incident_reference": inc.incident_reference or f"INC-{inc.id[:8].upper()}",
            "category": inc.category,
            "severity": inc.severity,
            "priority": inc.priority,
            "status": inc.status,
            "latitude": safe_lat,
            "longitude": safe_lon,
            "location_name": safe_location,
            "description": safe_desc[:200] + ("..." if len(safe_desc) > 200 else ""),
            "report_count": inc.report_count or 1,
            "created_at": inc.created_at.isoformat() if inc.created_at else None,
            "updated_at": inc.updated_at.isoformat() if inc.updated_at else None,
            "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
        }

    def _format_public_incident_detail(self, db: Session, inc: Incident) -> Dict[str, Any]:
        """Formats full public-safe incident detail with verified timeline and resolution evidence."""
        pub = inc.publication
        safe_lat, safe_lon = self._obfuscate_coords(
            pub.public_latitude if pub and pub.public_latitude else inc.latitude,
            pub.public_longitude if pub and pub.public_longitude else inc.longitude,
        )

        # Retrieve public citizen updates
        updates = (
            db.query(CitizenVisibleUpdate)
            .filter_by(incident_id=inc.id)
            .order_by(CitizenVisibleUpdate.created_at.asc())
            .all()
        )
        timeline = []
        for u in updates:
            timeline.append({
                "status_label": u.status_label,
                "message": u.public_message,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            })

        # Retrieve approved resolution evidence if incident is resolved
        resolution_data = None
        if inc.status in ["resolved", "closed"]:
            res = db.query(ResolutionRecord).filter_by(incident_id=inc.id).first()
            if res:
                before_url = None
                after_url = None
                if res.before_evidence_id:
                    ea_before = db.query(EvidenceAsset).filter_by(id=res.before_evidence_id).first()
                    if ea_before and ea_before.is_public:
                        before_url = f"/api/v1/evidence/{ea_before.id}/download"
                if res.after_evidence_id:
                    ea_after = db.query(EvidenceAsset).filter_by(id=res.after_evidence_id).first()
                    if ea_after and ea_after.is_public:
                        after_url = f"/api/v1/evidence/{ea_after.id}/download"

                resolution_data = {
                    "resolved_at": res.resolved_at.isoformat() if res.resolved_at else None,
                    "resolution_summary": res.resolution_notes,
                    "before_evidence_url": before_url,
                    "after_evidence_url": after_url,
                }

        return {
            "id": inc.id,
            "incident_reference": inc.incident_reference or f"INC-{inc.id[:8].upper()}",
            "category": inc.category,
            "severity": inc.severity,
            "priority": inc.priority,
            "status": inc.status,
            "latitude": safe_lat,
            "longitude": safe_lon,
            "location_name": (pub.public_location_name if pub and pub.public_location_name else inc.address) or "Civic Location",
            "title": (pub.public_title if pub and pub.public_title else f"{inc.category.replace('_', ' ').capitalize()} Incident"),
            "description": (pub.public_description if pub and pub.public_description else inc.description) or "",
            "report_count": inc.report_count or 1,
            "created_at": inc.created_at.isoformat() if inc.created_at else None,
            "updated_at": inc.updated_at.isoformat() if inc.updated_at else None,
            "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
            "timeline": timeline,
            "resolution": resolution_data,
        }
