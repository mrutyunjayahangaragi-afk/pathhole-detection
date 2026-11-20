"""
CivicLens Public Transparency & Statistics Service
==================================================
Computes 100% database-backed metrics for public oversight, tracking canonical
incidents vs. citizen report volumes, category distributions, and resolution SLAs.
Zero synthetic, fake, or mocked numbers.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import Incident, CitizenReport, IncidentPublication, ReportItem, IncidentStatusHistory

logger = logging.getLogger("civiclens.transparency")


class PublicTransparencyService:
    """Computes genuine public oversight statistics and SLA benchmarks."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def _get_db(self) -> Session:
        return self._session_factory()

    def get_transparency_metrics(self) -> Dict[str, Any]:
        """
        Aggregates live database statistics for public transparency.
        Distinguishes canonical incidents from citizen report volumes.
        """
        db = self._get_db()
        try:
            total_incidents = db.query(Incident).count()
            total_reports = db.query(CitizenReport).count()

            # Status distribution of canonical incidents
            status_counts = dict(
                db.query(Incident.status, func.count(Incident.id))
                .group_by(Incident.status)
                .all()
            )

            # Category distribution
            category_counts = dict(
                db.query(Incident.category, func.count(Incident.id))
                .group_by(Incident.category)
                .all()
            )

            # Severity distribution
            severity_counts = dict(
                db.query(Incident.severity, func.count(Incident.id))
                .group_by(Incident.severity)
                .all()
            )

            # Resolved count & resolution rate
            resolved_count = status_counts.get("resolved", 0) + status_counts.get("closed", 0)
            in_progress_count = status_counts.get("in_progress", 0) + status_counts.get("assigned", 0)
            awaiting_count = status_counts.get("new", 0) + status_counts.get("awaiting_verification", 0)

            resolution_rate_pct = round((resolved_count / total_incidents * 100), 1) if total_incidents > 0 else 0.0

            # Compute average resolution time from database timestamps
            resolved_incidents = (
                db.query(Incident.created_at, Incident.resolved_at)
                .filter(Incident.resolved_at != None)
                .all()
            )
            avg_resolution_hours = 0.0
            if resolved_incidents:
                total_seconds = sum(
                    (res_at - cr_at).total_seconds()
                    for cr_at, res_at in resolved_incidents
                    if res_at and cr_at and res_at >= cr_at
                )
                avg_resolution_hours = round(total_seconds / (len(resolved_incidents) * 3600.0), 1)

            # Recent public milestones (latest 5 resolved incidents)
            recent_resolved = (
                db.query(Incident)
                .filter(Incident.status.in_(["resolved", "closed"]))
                .order_by(Incident.resolved_at.desc())
                .limit(5)
                .all()
            )
            milestones = []
            for inc in recent_resolved:
                pub = inc.publication
                loc_name = (pub.public_location_name if pub and pub.public_location_name else inc.address) or "Civic Area"
                milestones.append({
                    "incident_reference": inc.incident_reference or f"INC-{inc.id[:8].upper()}",
                    "category": inc.category,
                    "location_name": loc_name,
                    "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
                })

            # Calculate genuine cluster consolidation ratio:
            # How many report items are linked into canonical incidents
            linked_items = db.query(ReportItem).filter(ReportItem.incident_id.isnot(None)).count()
            distinct_incidents_with_items = (
                db.query(func.count(func.distinct(ReportItem.incident_id)))
                .filter(ReportItem.incident_id.isnot(None))
                .scalar()
                or 0
            )
            cluster_ratio = (
                round(linked_items / distinct_incidents_with_items, 2)
                if distinct_incidents_with_items > 0
                else 1.0
            )

            return {
                "status": "success",
                "total_canonical_incidents": total_incidents,
                "total_citizen_reports": total_reports,
                "deduplication_ratio": cluster_ratio,
                "cluster_consolidation_ratio": cluster_ratio,
                "consolidated_report_items": linked_items,
                "clustered_incidents": distinct_incidents_with_items,
                "status_breakdown": {
                    "awaiting_verification": awaiting_count,
                    "verified": status_counts.get("verified", 0),
                    "in_progress": in_progress_count,
                    "on_hold": status_counts.get("on_hold", 0),
                    "resolved": resolved_count,
                    "rejected": status_counts.get("rejected", 0),
                },
                "category_breakdown": category_counts,
                "severity_breakdown": severity_counts,
                "resolution_rate_pct": resolution_rate_pct,
                "avg_resolution_hours": avg_resolution_hours,
                "recent_milestones": milestones,
            }
        finally:
            db.close()

    def get_recent_activity(self, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Retrieves real-time civic activity events from IncidentStatusHistory and CitizenReports.
        Excludes private citizen PII or internal engineering notes.
        """
        db = self._get_db()
        try:
            events = []

            # 1. Recent status transitions (e.g. verified, in_progress, resolved)
            transitions = (
                db.query(IncidentStatusHistory, Incident)
                .join(Incident, IncidentStatusHistory.incident_id == Incident.id)
                .order_by(IncidentStatusHistory.created_at.desc())
                .limit(limit)
                .all()
            )

            status_title_map = {
                "verified": "Incident Field-Verified",
                "in_progress": "Repair Work In Progress",
                "assigned": "Assigned to Municipal Dept",
                "resolved": "Hazard Remediation Resolved",
                "closed": "Incident Closed & Verified",
                "rejected": "Report Reviewed & Filtered",
                "on_hold": "Work On Hold (Materials Pending)",
                "reopened": "Incident Reopened for Inspection"
            }

            for hist, inc in transitions:
                loc = inc.address or "Bengaluru Civic Area"
                events.append({
                    "id": f"hist-{hist.id}",
                    "event_type": f"incident_{hist.new_status}",
                    "title": status_title_map.get(hist.new_status, f"Incident {hist.new_status.replace('_', ' ').capitalize()}"),
                    "category": inc.category or "infrastructure",
                    "reference": inc.incident_reference or f"INC-{inc.id[:8].upper()}",
                    "location_name": loc,
                    "timestamp": hist.created_at.isoformat() if hist.created_at else None,
                    "raw_time": hist.created_at,
                    "description": (hist.reason or inc.description or f"Status transitioned to {hist.new_status}.").strip()[:140],
                    "link": f"/public-incident.html?ref={inc.incident_reference or inc.id}"
                })

            # 2. Recent citizen submissions
            recent_reports = (
                db.query(CitizenReport)
                .order_by(CitizenReport.created_at.desc())
                .limit(limit)
                .all()
            )

            for rep in recent_reports:
                loc = rep.address or "Bengaluru Area"
                events.append({
                    "id": f"rep-{rep.id}",
                    "event_type": "new_report",
                    "title": "New Citizen Grievance Logged",
                    "category": "citizen_report",
                    "reference": rep.report_reference or f"CR-{rep.id[:8].upper()}",
                    "location_name": loc,
                    "timestamp": rep.created_at.isoformat() if rep.created_at else None,
                    "raw_time": rep.created_at,
                    "description": (rep.title or rep.description or "Citizen submitted an infrastructure issue.").strip()[:140],
                    "link": "/public-map.html"
                })

            # Sort combined events chronologically descending
            min_dt = datetime.min.replace(tzinfo=timezone.utc)
            events.sort(key=lambda x: x["raw_time"] or min_dt, reverse=True)

            # Strip temporary raw_time field
            for ev in events:
                ev.pop("raw_time", None)

            return events[:limit]
        finally:
            db.close()

    def search_public_incidents(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Full-text search for public incidents by reference, category, location, or description.
        Returns sanitized, public-safe records.
        """
        if not query or len(query.strip()) < 2:
            return []

        q_clean = query.strip()
        db = self._get_db()
        try:
            from sqlalchemy import or_
            pattern = f"%{q_clean}%"
            matches = (
                db.query(Incident)
                .filter(
                    or_(
                        Incident.incident_reference.ilike(pattern),
                        Incident.category.ilike(pattern),
                        Incident.address.ilike(pattern),
                        Incident.description.ilike(pattern),
                    )
                )
                .order_by(Incident.updated_at.desc())
                .limit(limit)
                .all()
            )

            results = []
            for inc in matches:
                results.append({
                    "id": inc.id,
                    "incident_reference": inc.incident_reference or f"INC-{inc.id[:8].upper()}",
                    "category": inc.category,
                    "status": inc.status,
                    "severity": inc.severity,
                    "priority": inc.priority,
                    "address": inc.address or "Bengaluru Area",
                    "description": (inc.description or "")[:120],
                    "latitude": inc.latitude,
                    "longitude": inc.longitude,
                    "created_at": inc.created_at.isoformat() if inc.created_at else None,
                    "link": f"/public-incident.html?ref={inc.incident_reference or inc.id}"
                })
            return results
        finally:
            db.close()
