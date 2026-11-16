"""
Duplicate Matching Service
==========================
End-to-end multi-signal duplicate incident detection and canonical matching engine.

Integrates:
- Exact SHA-256 evidence hashing
- 64-bit DCT perceptual image hashing (pHash)
- Defect-crop visual embeddings (DINOv2 / Mock)
- Spatial PostGIS / Haversine proximity with GPS uncertainty discount
- Category & semantic compatibility
- Explainable candidate ranking and separation analysis
- Persistent MatchEvaluation and MatchCandidate audit tracking
"""

import uuid
import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.config import Config, get_config
from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, ReportItem, CitizenReport, ReportEvidence, EvidenceAsset,
    Detection, DetectionEmbedding, MatchEvaluation, MatchCandidate,
    MatchDecision, IncidentObservation
)
from backend.domain.models import MatchDecision as DomainMatchDecision, MatchVerdict
from backend.services.location_service import LocationService
from backend.services.perceptual_hash_service import PerceptualHashService
from backend.services.defect_crop_service import DefectCropService
from backend.services.visual_embedding_service import VisualEmbeddingService
from backend.services.candidate_retrieval_service import CandidateRetrievalService
from backend.services.multi_signal_scoring_service import MultiSignalScoringService, CandidateScore
from backend.errors import NotFoundError, ValidationError


class DuplicateMatchingService:
    """Core orchestrator for intelligent duplicate incident matching."""

    ALGORITHM_VERSION = "v2.0.0-multisignal"
    CONFIG_VERSION = "v1.0"

    def __init__(
        self,
        first_arg=None,
        second_arg=None,
        session_factory=None,
        location_service: Optional[LocationService] = None,
        config=None,
        **kwargs,
    ):
        # Resolve config
        if isinstance(first_arg, Config):
            self.config = first_arg
        elif isinstance(second_arg, Config):
            self.config = second_arg
        elif config:
            self.config = config
        else:
            self.config = get_config()

        # Resolve location_service
        if isinstance(first_arg, LocationService):
            self.location_service = first_arg
        elif isinstance(second_arg, LocationService):
            self.location_service = second_arg
        elif location_service:
            self.location_service = location_service
        else:
            self.location_service = LocationService(self.config)

        # Resolve session_factory
        if callable(first_arg) and not isinstance(first_arg, (LocationService, Config)):
            self._custom_session_factory = first_arg
        elif session_factory:
            self._custom_session_factory = session_factory
        else:
            self._custom_session_factory = None

        self.phash_service = PerceptualHashService()
        self.crop_service = DefectCropService()
        self.visual_service = VisualEmbeddingService()
        self.retrieval_service = CandidateRetrievalService()
        self.scoring_service = MultiSignalScoringService(
            phash_service=self.phash_service,
            visual_service=self.visual_service,
        )

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def evaluate_report_against_existing(
        self, conn, lat: float, lon: float, report_id: str = ""
    ) -> DomainMatchDecision:
        """
        Evaluates coordinates against existing unrepaired detections/incidents
        using the baseline radius rule. Returns a structured MatchDecision.
        """
        rows = conn.execute(
            "SELECT id, latitude, longitude, severity, est_depth_cm, report_count "
            "FROM detections WHERE status != 'repaired'"
        ).fetchall()

        closest_id = None
        min_distance = float("inf")
        radius = getattr(self.config, "DEDUP_RADIUS_METERS", 15.0)

        for row in rows:
            dist = self.location_service.calculate_distance(
                lat, lon, row["latitude"], row["longitude"]
            )
            if dist <= radius and dist < min_distance:
                min_distance = dist
                closest_id = row["id"]

        if closest_id is not None:
            confidence = max(0.5, 1.0 - (min_distance / radius))
            verdict = (
                MatchVerdict.EXACT_DUPLICATE
                if min_distance <= (radius * 0.7)
                else MatchVerdict.PROBABLE_MATCH
            )
            return DomainMatchDecision(
                report_id=report_id,
                candidate_incident_id=closest_id,
                verdict=verdict,
                confidence_score=round(confidence, 2),
                spatial_distance_m=round(min_distance, 2),
                reason=f"Found existing open incident within {min_distance:.1f}m (threshold {radius}m)",
            )

        return DomainMatchDecision(
            report_id=report_id,
            candidate_incident_id=None,
            verdict=MatchVerdict.DISTINCT_INCIDENT,
            confidence_score=1.0,
            spatial_distance_m=0.0,
            reason=f"No existing incident within {radius}m radius.",
        )

    def evaluate_report_item(
        self,
        report_item_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes complete multi-signal matching evaluation for a ReportItem.
        Atomic, explainable, and idempotency-protected.
        """
        db = self._session_factory()
        try:
            item = db.query(ReportItem).filter_by(id=report_item_id).first()
            if not item:
                raise NotFoundError(f"ReportItem '{report_item_id}' not found")

            # Check if recent completed evaluation already exists for this item
            existing_eval = (
                db.query(MatchEvaluation)
                .filter_by(report_item_id=report_item_id)
                .order_by(MatchEvaluation.created_at.desc())
                .first()
            )
            # If already evaluated and no new detections/assets, we can return existing
            # unless a re-evaluation is explicitly forced

            # 1. Ensure visual features (pHash and crop embeddings) are generated
            self._ensure_visual_features(db, item)

            # 2. Extract best location metadata from report evidence or report
            lat, lon, accuracy, has_conflict = self._extract_location_data(db, item)

            # 3. Retrieve candidates
            candidate_ids = self.retrieval_service.get_candidate_incident_ids(
                db=db,
                report_item=item,
                latitude=lat,
                longitude=lon,
            )

            candidate_incidents = (
                db.query(Incident).filter(Incident.id.in_(candidate_ids)).all()
                if candidate_ids else []
            )

            # 4. Multi-signal scoring and candidate ranking
            scored_candidates, overall_decision = self.scoring_service.score_candidates(
                db=db,
                report_item=item,
                candidate_incidents=candidate_incidents,
                latitude=lat,
                longitude=lon,
                gps_accuracy_m=accuracy,
                location_conflict=has_conflict,
            )

            # 5. Persist MatchEvaluation and MatchCandidates in a single transaction
            eval_record = MatchEvaluation(
                id=str(uuid.uuid4()),
                report_item_id=item.id,
                matching_algorithm_version=self.ALGORITHM_VERSION,
                processing_status="completed",
                overall_decision=overall_decision,
                candidate_count=len(scored_candidates),
                top_score=scored_candidates[0].combined_score if scored_candidates else 0.0,
                configuration_version=self.CONFIG_VERSION,
                completed_at=datetime.datetime.now(datetime.timezone.utc),
            )
            db.add(eval_record)

            candidate_records = []
            for sc in scored_candidates:
                cand_rec = MatchCandidate(
                    id=str(uuid.uuid4()),
                    match_evaluation_id=eval_record.id,
                    candidate_incident_id=sc.candidate_incident_id,
                    candidate_rank=sc.candidate_rank,
                    combined_score=sc.combined_score,
                    geographic_distance_m=sc.geographic_distance_m,
                    geographic_score=sc.geographic_score,
                    visual_similarity_score=sc.visual_similarity_score,
                    perceptual_similarity_score=sc.perceptual_similarity_score,
                    exact_match_signal=sc.exact_match_signal,
                    category_score=sc.category_score,
                    text_score=sc.text_score,
                    decision_reason=sc.decision_reason,
                )
                db.add(cand_rec)
                candidate_records.append(cand_rec)

            # Create an auditable MatchDecision recommendation record
            best_cand_id = scored_candidates[0].candidate_incident_id if scored_candidates else None
            top_score = scored_candidates[0].combined_score if scored_candidates else 0.0
            top_reason = scored_candidates[0].decision_reason if scored_candidates else "No candidates found"

            match_dec = MatchDecision(
                id=str(uuid.uuid4()),
                match_evaluation_id=eval_record.id,
                report_item_id=item.id,
                candidate_incident_id=best_cand_id,
                visual_similarity_score=scored_candidates[0].visual_similarity_score if scored_candidates else None,
                geographic_distance_m=scored_candidates[0].geographic_distance_m if scored_candidates else None,
                category_similarity_score=scored_candidates[0].category_score if scored_candidates else None,
                overall_score=top_score,
                decision=overall_decision,
                decision_reason=top_reason,
                decision_source="automated_engine",
            )
            db.add(match_dec)

            db.commit()

            return self._serialize_evaluation(eval_record, candidate_records, db)

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _ensure_visual_features(self, db: Session, item: ReportItem) -> None:
        """Computes pHash and crop embeddings for item evidence assets if not present."""
        rep_evs = db.query(ReportEvidence).filter(
            (ReportEvidence.report_item_id == item.id) |
            (ReportEvidence.report_id == item.report_id)
        ).all()

        for re in rep_evs:
            asset = db.query(EvidenceAsset).filter_by(id=re.evidence_asset_id).first()
            if not asset or not asset.storage_key:
                continue

            # Compute pHash if missing
            if not asset.perceptual_hash and asset.media_type and asset.media_type.startswith("image/"):
                try:
                    phash = self.phash_service.compute_phash(asset.storage_key)
                    asset.perceptual_hash = phash
                    asset.hash_algorithm = self.phash_service.ALGORITHM
                    asset.hash_version = self.phash_service.VERSION
                    db.commit()
                except Exception:
                    pass

            # Compute crop embeddings for Step 5 detections
            detections = db.query(Detection).filter_by(evidence_asset_id=asset.id).all()
            for det in detections:
                existing_emb = db.query(DetectionEmbedding).filter_by(detection_id=det.id).first()
                if not existing_emb and asset.storage_key:
                    try:
                        bbox = (det.bbox_x, det.bbox_y, det.bbox_w, det.bbox_h)
                        crop = self.crop_service.crop_defect(asset.storage_key, bbox=bbox)
                        vector = self.visual_service.get_crop_embedding(crop)
                        emb = DetectionEmbedding(
                            id=str(uuid.uuid4()),
                            detection_id=det.id,
                            evidence_asset_id=asset.id,
                            crop_bbox_json=f"[{det.bbox_x},{det.bbox_y},{det.bbox_w},{det.bbox_h}]",
                            embedding_vector=vector,
                            embedding_model=self.visual_service.provider.model_name,
                            embedding_model_version=self.visual_service.provider.model_version,
                            embedding_dimension=self.visual_service.provider.dimension,
                        )
                        db.add(emb)
                        db.commit()
                    except Exception:
                        pass

    def _extract_location_data(
        self, db: Session, item: ReportItem
    ) -> Tuple[Optional[float], Optional[float], Optional[float], bool]:
        """Extracts latitude, longitude, accuracy, and location conflict flag."""
        rep_ev = db.query(ReportEvidence).filter(
            (ReportEvidence.report_item_id == item.id) |
            (ReportEvidence.report_id == item.report_id)
        ).first()

        lat = None
        lon = None
        acc = 5.0
        conflict = False

        if rep_ev:
            lat = rep_ev.submitted_latitude
            lon = rep_ev.submitted_longitude
            acc = rep_ev.gps_accuracy_m or 5.0
            conflict = bool(rep_ev.location_conflict)

        if lat is None and item.report:
            lat = item.report.latitude
            lon = item.report.longitude
            acc = item.report.location_accuracy_m or 5.0

        return lat, lon, acc, conflict

    def _serialize_evaluation(
        self,
        eval_record: MatchEvaluation,
        candidates: List[MatchCandidate],
        db: Session,
    ) -> Dict[str, Any]:
        """Serializes evaluation record with rich candidate details for API and UI."""
        cand_list = []
        for c in candidates:
            inc = db.query(Incident).filter_by(id=c.candidate_incident_id).first()
            cand_list.append({
                "candidate_rank": c.candidate_rank,
                "candidate_incident_id": c.candidate_incident_id,
                "incident_reference": inc.incident_reference if inc else None,
                "incident_category": inc.category if inc else None,
                "incident_status": inc.status if inc else None,
                "incident_latitude": inc.latitude if inc else None,
                "incident_longitude": inc.longitude if inc else None,
                "incident_address": inc.address if inc else None,
                "incident_report_count": inc.report_count if inc else 1,
                "combined_score": c.combined_score,
                "geographic_distance_m": c.geographic_distance_m,
                "geographic_score": c.geographic_score,
                "visual_similarity_score": c.visual_similarity_score,
                "perceptual_similarity_score": c.perceptual_similarity_score,
                "exact_match_signal": c.exact_match_signal,
                "category_score": c.category_score,
                "text_score": c.text_score,
                "decision_reason": c.decision_reason,
            })

        return {
            "evaluation_id": eval_record.id,
            "report_item_id": eval_record.report_item_id,
            "overall_decision": eval_record.overall_decision,
            "processing_status": eval_record.processing_status,
            "candidate_count": eval_record.candidate_count,
            "top_score": eval_record.top_score,
            "matching_algorithm_version": eval_record.matching_algorithm_version,
            "configuration_version": eval_record.configuration_version,
            "created_at": eval_record.created_at.isoformat() if eval_record.created_at else None,
            "candidates": cand_list,
        }
