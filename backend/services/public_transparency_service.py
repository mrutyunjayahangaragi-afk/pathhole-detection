"""
CivicLens Public Transparency & Statistics Service
==================================================
Computes 100% database-backed metrics for public oversight, tracking canonical
incidents vs. citizen report volumes, category distributions, and resolution SLAs.
Zero synthetic, fake, or mocked numbers.
"""

import logging
from typing import Dict, Any, List
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import Incident, CitizenReport, IncidentPublication, ReportItem

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
