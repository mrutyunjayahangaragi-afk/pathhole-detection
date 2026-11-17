"""
Evidence Repository
===================
Persistence operations for evidence assets, SHA-256 deduplication, and media metadata.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.db.models import EvidenceAsset, ReportEvidence


class EvidenceRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_evidence(self, data: Dict[str, Any]) -> EvidenceAsset:
        """Persists a new evidence asset record."""
        asset = EvidenceAsset(**data)
        self.session.add(asset)
        self.session.flush()
        return asset

    def get_by_id(self, evidence_id: str) -> Optional[EvidenceAsset]:
        """Retrieves an evidence asset by its primary key UUID."""
        return self.session.query(EvidenceAsset).filter_by(id=evidence_id).first()

    def get_by_sha256(self, sha256_hash: str) -> Optional[EvidenceAsset]:
        """Finds an existing asset matching the cryptographic SHA-256 digest."""
        return self.session.query(EvidenceAsset).filter_by(content_sha256=sha256_hash).first()

    def get_evidence_for_report(self, report_id: str) -> List[EvidenceAsset]:
        """Retrieves all evidence assets linked to a report."""
        return (
            self.session.query(EvidenceAsset)
            .join(ReportEvidence, ReportEvidence.evidence_asset_id == EvidenceAsset.id)
            .filter(ReportEvidence.report_id == report_id)
            .all()
        )
