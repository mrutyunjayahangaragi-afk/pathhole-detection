"""
Report Repository
=================
Persistence operations for citizen reports, report items, and linked evidence.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.db.models import CitizenReport, ReportItem, ReportEvidence


class ReportRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_report(self, data: Dict[str, Any]) -> CitizenReport:
        """Persists a new citizen report."""
        report = CitizenReport(**data)
        self.session.add(report)
        self.session.flush()
        return report

    def get_by_id(self, report_id: str) -> Optional[CitizenReport]:
        """Retrieves a report by its primary UUID."""
        return self.session.query(CitizenReport).filter_by(id=report_id).first()

    def get_by_reference(self, reference: str) -> Optional[CitizenReport]:
        """Retrieves a report by its public tracking reference."""
        return self.session.query(CitizenReport).filter_by(report_reference=reference).first()

    def get_citizen_reports(
        self, citizen_id: str, limit: int = 50, offset: int = 0
    ) -> List[CitizenReport]:
        """Retrieves paginated reports submitted by a specific citizen."""
        return (
            self.session.query(CitizenReport)
            .filter_by(citizen_id=citizen_id)
            .order_by(CitizenReport.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def add_report_item(self, item_data: Dict[str, Any]) -> ReportItem:
        """Adds an individual line-item defect to a report."""
        item = ReportItem(**item_data)
        self.session.add(item)
        self.session.flush()
        return item

    def get_report_items(self, report_id: str) -> List[ReportItem]:
        """Retrieves all defect items belonging to a report."""
        return (
            self.session.query(ReportItem)
            .filter_by(report_id=report_id)
            .order_by(ReportItem.item_order.asc())
            .all()
        )

    def link_evidence(self, report_id: str, evidence_asset_id: str) -> ReportEvidence:
        """Associates an evidence asset with a report."""
        assoc = ReportEvidence(
            report_id=report_id,
            evidence_asset_id=evidence_asset_id
        )
        self.session.add(assoc)
        self.session.flush()
        return assoc
