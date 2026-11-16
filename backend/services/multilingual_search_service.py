"""
Multilingual Search Service
===========================
Executes search queries across original Kannada, English, mixed script,
and translated text, report reference codes, categories, and normalized address data.
Applies strict role-based access control to protect citizen privacy.
"""

from typing import Dict, Any, List, Optional
from sqlalchemy import or_, and_, text

from backend.db.engine import get_session_factory
from backend.db.models import (
    CitizenReport, ReportItem, ReportTranslation, LocationRecord, User
)


class MultilingualSearchService:
    """Provides privacy-safe, multilingual search across civic grievance reports."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def search_reports(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        language: Optional[str] = None,
        requesting_user: Optional[User] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """
        Searches reports with multilingual matching and role-based scoping.
        Citizens can only search their own reports; municipal staff search system-wide.
        """
        db = self._session_factory()
        try:
            q = db.query(CitizenReport)

            # 1. Authorization Scoping
            if not requesting_user or requesting_user.role == "citizen":
                user_id = requesting_user.id if requesting_user else "__none__"
                q = q.filter(CitizenReport.citizen_id == user_id)

            # 2. Category & Status filters
            if category and category.strip():
                cat_clean = category.strip().lower()
                q = q.join(ReportItem, CitizenReport.id == ReportItem.report_id).filter(
                    ReportItem.category == cat_clean
                )

            if status and status.strip():
                q = q.filter(CitizenReport.status == status.strip().lower())

            if language and language.strip():
                q = q.filter(
                    or_(
                        CitizenReport.original_language == language.strip().lower(),
                        CitizenReport.detected_language == language.strip().lower(),
                    )
                )

            # 3. Multilingual Query Matching
            if query and query.strip():
                search_term = query.strip()
                like_term = f"%{search_term}%"

                # Subquery for matching translations
                matching_trans_reports = (
                    db.query(ReportTranslation.report_id)
                    .filter(
                        or_(
                            ReportTranslation.translated_text.ilike(like_term),
                            ReportTranslation.original_text.ilike(like_term),
                        )
                    )
                )

                # Subquery for matching structured location records
                matching_loc_reports = (
                    db.query(LocationRecord.report_id)
                    .filter(
                        or_(
                            LocationRecord.road_name.ilike(like_term),
                            LocationRecord.locality.ilike(like_term),
                            LocationRecord.city.ilike(like_term),
                            LocationRecord.district.ilike(like_term),
                            LocationRecord.postal_code.ilike(like_term),
                        )
                    )
                )

                q = q.filter(
                    or_(
                        CitizenReport.report_reference.ilike(like_term),
                        CitizenReport.title.ilike(like_term),
                        CitizenReport.description.ilike(like_term),
                        CitizenReport.translated_description.ilike(like_term),
                        CitizenReport.address.ilike(like_term),
                        CitizenReport.id.in_(matching_trans_reports),
                        CitizenReport.id.in_(matching_loc_reports),
                    )
                )

            total_count = q.count()
            offset = max(0, (page - 1) * per_page)
            reports = q.order_by(CitizenReport.created_at.desc()).offset(offset).limit(per_page).all()

            results = []
            for r in reports:
                items = db.query(ReportItem).filter_by(report_id=r.id).all()
                primary_cat = items[0].category if items else "pothole"

                results.append({
                    "id": r.id,
                    "report_reference": r.report_reference,
                    "title": r.title,
                    "description": r.description,
                    "translated_description": r.translated_description,
                    "original_language": r.original_language,
                    "detected_language": r.detected_language,
                    "category": primary_cat,
                    "status": r.status,
                    "severity": r.reported_severity,
                    "address": r.address,
                    "latitude": r.latitude,
                    "longitude": r.longitude,
                    "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                })

            return {
                "reports": results,
                "total": total_count,
                "page": page,
                "per_page": per_page,
                "pages": (total_count + per_page - 1) // per_page if per_page else 1,
            }
        finally:
            db.close()
