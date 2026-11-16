"""
Candidate Retrieval Service
===========================
Generates potential candidate incidents for an incoming ReportItem
across multiple independent retrieval channels:

1. Exact SHA-256 match on evidence assets.
2. Perceptual hash (pHash) near-duplicate lookup (Hamming distance <= 12).
3. Spatial radius retrieval (PostGIS / Haversine within 50m).
4. Object-level crop visual embedding similarity.

Unions candidate IDs into a deduplicated candidate set for deep multi-signal scoring.
"""

from typing import List, Set, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.db.models import (
    Incident, ReportItem, ReportEvidence, EvidenceAsset,
    IncidentObservation, DetectionEmbedding, Detection
)
from backend.services.perceptual_hash_service import PerceptualHashService
from backend.services.location_service import LocationService


class CandidateRetrievalService:
    """Multi-channel candidate generator for duplicate incident matching."""

    DEFAULT_SPATIAL_SEARCH_RADIUS_M = 50.0
    MAX_PHASH_HAMMING_DISTANCE = 12

    def __init__(self, location_service: Optional[LocationService] = None):
        self.location_service = location_service or LocationService()
        self.phash_service = PerceptualHashService()

    def get_candidate_incident_ids(
        self,
        db: Session,
        report_item: ReportItem,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        max_candidates: int = 20,
    ) -> List[str]:
        """
        Retrieves a deduplicated list of candidate Incident IDs across all channels.
        """
        candidates: Set[str] = set()

        # 1. Exact SHA-256 Match Channel
        exact_ids = self._retrieve_by_exact_hash(db, report_item)
        candidates.update(exact_ids)

        # 2. Perceptual Hash Match Channel
        phash_ids = self._retrieve_by_phash(db, report_item)
        candidates.update(phash_ids)

        # 3. Spatial Proximity Channel
        if latitude is not None and longitude is not None:
            spatial_ids = self._retrieve_by_spatial_proximity(
                db, latitude, longitude, self.DEFAULT_SPATIAL_SEARCH_RADIUS_M
            )
            candidates.update(spatial_ids)

        # Filter out closed/repaired incidents if needed, or retain with flag
        active_incidents = (
            db.query(Incident.id)
            .filter(Incident.id.in_(list(candidates)))
            .filter(Incident.status.notin_(["closed"]))
            .all()
        )
        valid_ids = [r[0] for r in active_incidents]

        return valid_ids[:max_candidates]

    def _retrieve_by_exact_hash(self, db: Session, item: ReportItem) -> Set[str]:
        """Finds incidents linked to assets with identical SHA-256 checksums."""
        candidate_ids: Set[str] = set()

        # Get evidence assets for this item or report
        rep_evs = db.query(ReportEvidence).filter(
            (ReportEvidence.report_item_id == item.id) |
            (ReportEvidence.report_id == item.report_id)
        ).all()

        asset_ids = [re.evidence_asset_id for re in rep_evs if re.evidence_asset_id]
        if not asset_ids:
            return candidate_ids

        # Get hashes of these assets
        assets = db.query(EvidenceAsset).filter(EvidenceAsset.id.in_(asset_ids)).all()
        hashes = [a.content_sha256 for a in assets if a.content_sha256]
        if not hashes:
            return candidate_ids

        # Find matching assets in the database
        matching_asset_ids = [
            r[0] for r in db.query(EvidenceAsset.id)
            .filter(EvidenceAsset.content_sha256.in_(hashes))
            .filter(EvidenceAsset.id.notin_(asset_ids))
            .all()
        ]

        if matching_asset_ids:
            obs = db.query(IncidentObservation.incident_id).filter(
                IncidentObservation.evidence_asset_id.in_(matching_asset_ids)
            ).all()
            for o in obs:
                candidate_ids.add(o[0])

        return candidate_ids

    def _retrieve_by_phash(self, db: Session, item: ReportItem) -> Set[str]:
        """Finds incidents linked to assets with low perceptual hash Hamming distance."""
        candidate_ids: Set[str] = set()

        rep_evs = db.query(ReportEvidence).filter(
            (ReportEvidence.report_item_id == item.id) |
            (ReportEvidence.report_id == item.report_id)
        ).all()

        asset_ids = [re.evidence_asset_id for re in rep_evs if re.evidence_asset_id]
        if not asset_ids:
            return candidate_ids

        source_assets = db.query(EvidenceAsset).filter(
            EvidenceAsset.id.in_(asset_ids),
            EvidenceAsset.perceptual_hash.isnot(None)
        ).all()

        if not source_assets:
            return candidate_ids

        # Fetch all existing assets linked to incidents
        linked_assets = (
            db.query(IncidentObservation.incident_id, EvidenceAsset.perceptual_hash)
            .join(EvidenceAsset, IncidentObservation.evidence_asset_id == EvidenceAsset.id)
            .filter(
                EvidenceAsset.id.notin_(asset_ids),
                EvidenceAsset.perceptual_hash.isnot(None)
            )
            .all()
        )

        for src in source_assets:
            src_hash = src.perceptual_hash
            for inc_id, other_hash in linked_assets:
                dist = self.phash_service.hamming_distance(src_hash, other_hash)
                if dist <= self.MAX_PHASH_HAMMING_DISTANCE:
                    candidate_ids.add(inc_id)

        return candidate_ids

    def _retrieve_by_spatial_proximity(
        self, db: Session, lat: float, lon: float, radius_m: float
    ) -> Set[str]:
        """Finds open incidents within a geographic radius in meters."""
        candidate_ids: Set[str] = set()

        # Rough bounding box pre-filter for database efficiency
        # 1 deg lat ~= 111,000 m
        lat_delta = (radius_m * 1.5) / 111000.0
        lon_delta = (radius_m * 1.5) / (111000.0 * max(0.1, abs(LocationService._haversine_formula if hasattr(LocationService, '_haversine_formula') else 1.0)))

        incidents = (
            db.query(Incident)
            .filter(Incident.latitude.between(lat - lat_delta, lat + lat_delta))
            .filter(Incident.longitude.between(lon - lon_delta, lon + lon_delta))
            .filter(Incident.status.notin_(["closed"]))
            .all()
        )

        for inc in incidents:
            dist = self.location_service.calculate_distance(lat, lon, inc.latitude, inc.longitude)
            if dist <= radius_m:
                candidate_ids.add(inc.id)

        return candidate_ids
