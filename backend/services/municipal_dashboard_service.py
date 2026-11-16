"""
CivicLens Municipal Dashboard & Metrics Service
===============================================
Delivers 100% database-backed operations statistics, triage queue retrieval,
SLA compliance auditing, and departmental workload distribution.
Zero hardcoded or fake numbers.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, Department, User, CitizenReport, ReportItem, ReportEvidence,
    EvidenceAsset, InspectionRecord, ResolutionRecord
)
from backend.services.incident_state_machine_service import IncidentStatus


# SLA Maximum Target Hours by Priority
SLA_TARGET_HOURS = {
    "critical": 24,
    "high": 48,
    "normal": 168,  # 7 days
    "low": 336      # 14 days
}


class MunicipalDashboardService:
    """Provides high-performance database-driven analytics and triage queue views."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def get_dashboard_metrics(self, department_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Computes accurate aggregate incident metrics directly from database tables.
        Zero hardcoded or placeholder values.
        """
        db: Session = self._session_factory()
        now = datetime.now(timezone.utc)
        try:
            base_query = db.query(Incident)
            if department_id:
                base_query = base_query.filter(Incident.department_id == department_id)

            total_registered = base_query.count()

            awaiting_verification = base_query.filter(
                Incident.status.in_([IncidentStatus.NEW, IncidentStatus.AWAITING_VERIFICATION])
            ).count()

            in_progress = base_query.filter(
                Incident.status.in_([IncidentStatus.ASSIGNED, IncidentStatus.IN_PROGRESS])
            ).count()

            on_hold = base_query.filter(
                Incident.status == IncidentStatus.ON_HOLD
            ).count()

            resolved = base_query.filter(
                Incident.status.in_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED])
            ).count()

            rejected = base_query.filter(
                Incident.status == IncidentStatus.REJECTED
            ).count()

            # SLA breaches calculation across active incidents
            active_incidents = base_query.filter(
                ~Incident.status.in_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED, IncidentStatus.REJECTED])
            ).all()

            overdue_sla_count = 0
            for inc in active_incidents:
                created = inc.created_at
                if created:
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    age_hours = (now - created).total_seconds() / 3600.0
                    target_hours = SLA_TARGET_HOURS.get(inc.priority or "normal", 168)
                    if age_hours > target_hours:
                        overdue_sla_count += 1

            # Breakdown by Category
            cat_rows = db.query(
                Incident.category, func.count(Incident.id)
            )
            if department_id:
                cat_rows = cat_rows.filter(Incident.department_id == department_id)
            cat_rows = cat_rows.group_by(Incident.category).all()
            by_category = {cat or "unknown": cnt for cat, cnt in cat_rows}

            # Breakdown by Priority
            prio_rows = db.query(
                Incident.priority, func.count(Incident.id)
            )
            if department_id:
                prio_rows = prio_rows.filter(Incident.department_id == department_id)
            prio_rows = prio_rows.group_by(Incident.priority).all()
            by_priority = {prio or "normal": cnt for prio, cnt in prio_rows}

            # Department Workload Summary
            dept_summary = []
            departments = db.query(Department).filter_by(is_active=True).all()
            for d in departments:
                dept_active = db.query(func.count(Incident.id)).filter(
                    Incident.department_id == d.id,
                    ~Incident.status.in_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED, IncidentStatus.REJECTED])
                ).scalar() or 0

                dept_resolved = db.query(func.count(Incident.id)).filter(
                    Incident.department_id == d.id,
                    Incident.status.in_([IncidentStatus.RESOLVED, IncidentStatus.CLOSED])
                ).scalar() or 0

                dept_summary.append({
                    "id": d.id,
                    "code": d.code,
                    "name": d.name,
                    "active_incidents": dept_active,
                    "resolved_incidents": dept_resolved
                })

            return {
                "total_registered": total_registered,
                "awaiting_verification": awaiting_verification,
                "in_progress": in_progress,
                "on_hold": on_hold,
                "resolved": resolved,
                "rejected": rejected,
                "overdue_sla_count": overdue_sla_count,
                "by_category": by_category,
                "by_priority": by_priority,
                "department_summary": dept_summary,
                "generated_at": now.isoformat()
            }
        finally:
            db.close()

    def list_triage_incidents(
        self,
        department_id: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        officer_id: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Queries canonical incidents for the municipal triage queue with pagination and filters."""
        limit = min(max(1, limit), 200)
        offset = max(0, offset)

        db: Session = self._session_factory()
        now = datetime.now(timezone.utc)
        try:
            query = db.query(Incident)

            if department_id:
                query = query.filter(Incident.department_id == department_id)
            if status:
                query = query.filter(Incident.status == status)
            if priority:
                query = query.filter(Incident.priority == priority)
            if officer_id:
                query = query.filter(Incident.assigned_officer_id == officer_id)

            if search_query and search_query.strip():
                term = f"%{search_query.strip()}%"
                query = query.filter(
                    or_(
                        Incident.id.ilike(term),
                        Incident.description.ilike(term),
                        Incident.category.ilike(term)
                    )
                )

            total_matching = query.count()
            incidents = query.order_by(Incident.created_at.desc()).limit(limit).offset(offset).all()

            results = []
            for inc in incidents:
                # Resolve department name
                dept_name = None
                dept_code = None
                if inc.department_id:
                    d = db.query(Department).filter_by(id=inc.department_id).first()
                    if d:
                        dept_name = d.name
                        dept_code = d.code

                # Resolve officer name
                officer_name = None
                if inc.assigned_officer_id:
                    u = db.query(User).filter_by(id=inc.assigned_officer_id).first()
                    if u:
                        officer_name = u.display_name

                # Count linked citizen reports
                report_count = db.query(func.count(CitizenReport.id)).join(
                    ReportItem, ReportItem.report_id == CitizenReport.id
                ).filter(
                    ReportItem.incident_id == inc.id
                ).scalar() or 0

                # Formulate human-friendly reference: INC-YYYYMM-XXXXX
                created_dt = inc.created_at or now
                ref_id = f"INC-{created_dt.strftime('%Y%m')}-{inc.id[:5].upper()}"

                # Calculate SLA status
                created = inc.created_at or now
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_hours = (now - created).total_seconds() / 3600.0
                target_hours = SLA_TARGET_HOURS.get(inc.priority or "normal", 168)
                is_sla_breached = (
                    age_hours > target_hours and
                    inc.status not in [IncidentStatus.RESOLVED, IncidentStatus.CLOSED, IncidentStatus.REJECTED]
                )

                results.append({
                    "id": inc.id,
                    "reference": inc.incident_reference or ref_id,
                    "title": inc.description or f"{inc.category.replace('_', ' ').capitalize()} defect",
                    "category": inc.category,
                    "status": inc.status,
                    "priority": inc.priority or "normal",
                    "department_id": inc.department_id,
                    "department_name": dept_name,
                    "department_code": dept_code,
                    "assigned_officer_id": inc.assigned_officer_id,
                    "assigned_officer_name": officer_name,
                    "latitude": inc.latitude,
                    "longitude": inc.longitude,
                    "reports_count": report_count,
                    "age_hours": round(age_hours, 1),
                    "is_sla_breached": is_sla_breached,
                    "created_at": inc.created_at.isoformat() if inc.created_at else None,
                    "updated_at": inc.updated_at.isoformat() if inc.updated_at else None
                })

            return {
                "total": total_matching,
                "limit": limit,
                "offset": offset,
                "incidents": results
            }
        finally:
            db.close()
