"""
Multi-Signal Scoring Service
============================
Evaluates a ReportItem against candidate Incidents using independent evidence signals:

1. Exact SHA-256 match signal
2. Perceptual hash (pHash) similarity
3. Defect-crop visual embedding cosine similarity
4. Geographic proximity with GPS uncertainty discount
5. Defect category compatibility
6. Semantic text similarity

Produces an explainable, calibrated composite score, candidate ranking,
score separation analysis, and classified decision.
"""

from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from backend.db.models import (
    Incident, ReportItem, ReportEvidence, EvidenceAsset,
    IncidentObservation, Detection, DetectionEmbedding
)
from backend.services.perceptual_hash_service import PerceptualHashService
from backend.services.visual_embedding_service import VisualEmbeddingService
from backend.services.location_service import LocationService


COMPATIBLE_CATEGORIES = {
    "pothole": {"pothole", "road_damage"},
    "road_damage": {"road_damage", "pothole"},
    "garbage": {"garbage", "drainage"},
    "drainage": {"drainage", "water_leakage", "garbage"},
    "water_leakage": {"water_leakage", "drainage"},
    "broken_streetlight": {"broken_streetlight"},
}


class CandidateScore:
    """Detailed score breakdown for a single candidate incident."""
    def __init__(
        self,
        candidate_incident_id: str,
        combined_score: float,
        exact_match_signal: bool,
        geographic_distance_m: Optional[float],
        geographic_score: Optional[float],
        visual_similarity_score: Optional[float],
        perceptual_similarity_score: Optional[float],
        category_score: float,
        text_score: Optional[float],
        decision_reason: str,
        candidate_rank: int = 1,
    ):
        self.candidate_incident_id = candidate_incident_id
        self.combined_score = round(combined_score, 4)
        self.exact_match_signal = exact_match_signal
        self.geographic_distance_m = geographic_distance_m
        self.geographic_score = geographic_score
        self.visual_similarity_score = visual_similarity_score
        self.perceptual_similarity_score = perceptual_similarity_score
        self.category_score = category_score
        self.text_score = text_score
        self.decision_reason = decision_reason
        self.candidate_rank = candidate_rank


class MultiSignalScoringService:
    """Computes explainable, multi-signal candidate scores and overall matching decisions."""

    WEIGHT_GEO = 0.35
    WEIGHT_VIS = 0.30
    WEIGHT_PHASH = 0.15
    WEIGHT_CAT = 0.15
    WEIGHT_TEXT = 0.05

    def __init__(
        self,
        location_service: Optional[LocationService] = None,
        phash_service: Optional[PerceptualHashService] = None,
        visual_service: Optional[VisualEmbeddingService] = None,
    ):
        self.location_service = location_service or LocationService()
        self.phash_service = phash_service or PerceptualHashService()
        self.visual_service = visual_service or VisualEmbeddingService()

    def score_candidates(
        self,
        db: Session,
        report_item: ReportItem,
        candidate_incidents: List[Incident],
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        gps_accuracy_m: Optional[float] = None,
        location_conflict: bool = False,
    ) -> Tuple[List[CandidateScore], str]:
        """
        Scores and ranks candidate incidents for a report item.

        Returns:
            Tuple of (Ranked CandidateScores, Overall Decision String)
        """
        if not candidate_incidents:
            decision = "INSUFFICIENT_EVIDENCE" if (latitude is None and not report_item.report.evidence_links.count()) else "NEW_INCIDENT"
            return [], decision

        # Pre-fetch item's evidence and embeddings
        item_assets, item_embeddings = self._get_item_assets_and_embeddings(db, report_item)

        scored_candidates: List[CandidateScore] = []

        for inc in candidate_incidents:
            score_data = self._score_single_candidate(
                db=db,
                report_item=report_item,
                candidate=inc,
                item_assets=item_assets,
                item_embeddings=item_embeddings,
                lat=latitude,
                lon=longitude,
                gps_accuracy_m=gps_accuracy_m,
            )
            scored_candidates.append(score_data)

        # Sort by combined score descending
        scored_candidates.sort(key=lambda c: c.combined_score, reverse=True)

        # Assign ranks
        for idx, sc in enumerate(scored_candidates):
            sc.candidate_rank = idx + 1

        # Classify overall decision
        top = scored_candidates[0]
        runner_up = scored_candidates[1] if len(scored_candidates) > 1 else None

        decision = self._classify_decision(
            top_candidate=top,
            runner_up=runner_up,
            location_conflict=location_conflict,
        )

        return scored_candidates, decision

    def _score_single_candidate(
        self,
        db: Session,
        report_item: ReportItem,
        candidate: Incident,
        item_assets: List[EvidenceAsset],
        item_embeddings: List[List[float]],
        lat: Optional[float],
        lon: Optional[float],
        gps_accuracy_m: Optional[float],
    ) -> CandidateScore:
        reasons = []

        # 1. Exact SHA-256 match check
        exact_match = False
        inc_assets = self._get_incident_assets(db, candidate.id)
        inc_hashes = {a.content_sha256 for a in inc_assets if a.content_sha256}
        for a in item_assets:
            if a.content_sha256 and a.content_sha256 in inc_hashes:
                exact_match = True
                reasons.append("Identical image file bytes uploaded (SHA-256 match)")
                break

        # 2. Geographic score
        geo_dist = None
        geo_score = None
        if lat is not None and lon is not None:
            dist = self.location_service.calculate_distance(lat, lon, candidate.latitude, candidate.longitude)
            geo_dist = round(dist, 2)
            acc = (gps_accuracy_m or 5.0)
            eff_dist = max(0.0, dist - acc)

            if eff_dist <= 5.0:
                geo_score = max(0.95, 1.0 - (eff_dist / 100.0))
                reasons.append(f"Immediate physical proximity ({dist:.1f}m away)")
            elif eff_dist <= 25.0:
                geo_score = 0.95 - 0.35 * ((eff_dist - 5.0) / 20.0)
                reasons.append(f"Close road proximity ({dist:.1f}m away)")
            elif eff_dist <= 50.0:
                geo_score = 0.60 - 0.40 * ((eff_dist - 25.0) / 25.0)
                reasons.append(f"Nearby on same street/area ({dist:.1f}m away)")
            else:
                geo_score = 0.0
                reasons.append(f"Farther geographic distance ({dist:.1f}m away)")

        # 3. Perceptual Hash similarity
        phash_score = None
        max_phash_sim = 0.0
        for src_a in item_assets:
            if not src_a.perceptual_hash:
                continue
            for inc_a in inc_assets:
                if not inc_a.perceptual_hash:
                    continue
                sim = self.phash_service.similarity(src_a.perceptual_hash, inc_a.perceptual_hash)
                if sim > max_phash_sim:
                    max_phash_sim = sim

        if max_phash_sim > 0.0:
            phash_score = round(max_phash_sim, 4)
            if phash_score >= 0.85:
                reasons.append(f"High perceptual image similarity ({phash_score:.2f})")
            elif phash_score >= 0.70:
                reasons.append(f"Moderate perceptual image similarity ({phash_score:.2f})")

        # 4. Defect-crop Visual Embedding similarity
        vis_score = None
        inc_embeddings = self._get_incident_embeddings(db, candidate.id)
        max_vis_sim = 0.0
        for u in item_embeddings:
            for v in inc_embeddings:
                sim = self.visual_service.cosine_similarity(u, v)
                if sim > max_vis_sim:
                    max_vis_sim = sim

        if max_vis_sim > 0.0:
            vis_score = round(max_vis_sim, 4)
            if vis_score >= 0.80:
                reasons.append(f"Defect crop appearance strongly matches ({vis_score:.2f})")
            elif vis_score >= 0.60:
                reasons.append(f"Defect crop appearance moderately matches ({vis_score:.2f})")

        # 5. Category compatibility
        item_cat = (report_item.category or "pothole").lower().strip()
        cand_cat = (candidate.category or "pothole").lower().strip()

        if item_cat == cand_cat:
            cat_score = 1.0
            reasons.append(f"Identical defect category ({item_cat})")
        elif cand_cat in COMPATIBLE_CATEGORIES.get(item_cat, set()):
            cat_score = 0.70
            reasons.append(f"Compatible defect category ({item_cat} vs {cand_cat})")
        else:
            cat_score = 0.0
            reasons.append(f"Incompatible category ({item_cat} vs {cand_cat})")

        # 6. Text description similarity
        text_score = self._compute_text_similarity(report_item.description, candidate.description)
        if text_score is not None and text_score > 0.40:
            reasons.append("Citizen descriptions share significant keyword overlap")

        # 7. Composite score calculation
        available_weights = 0.0
        weighted_sum = 0.0

        if geo_score is not None:
            weighted_sum += self.WEIGHT_GEO * geo_score
            available_weights += self.WEIGHT_GEO

        if vis_score is not None:
            weighted_sum += self.WEIGHT_VIS * vis_score
            available_weights += self.WEIGHT_VIS

        if phash_score is not None:
            weighted_sum += self.WEIGHT_PHASH * phash_score
            available_weights += self.WEIGHT_PHASH

        weighted_sum += self.WEIGHT_CAT * cat_score
        available_weights += self.WEIGHT_CAT

        if text_score is not None:
            weighted_sum += self.WEIGHT_TEXT * text_score
            available_weights += self.WEIGHT_TEXT

        base_composite = (weighted_sum / available_weights) if available_weights > 0 else 0.0

        # Exact file match floor boost
        if exact_match and base_composite < 0.85 and cat_score > 0.0:
            base_composite = max(base_composite, 0.88)

        # Incompatible category hard clamp
        if cat_score == 0.0:
            base_composite = min(base_composite, 0.30)

        # Far distance (> 100m) hard clamp unless exact SHA-256 match
        if geo_dist is not None and geo_dist > 100.0 and not exact_match:
            base_composite = min(base_composite, 0.35)

        combined_score = max(0.0, min(1.0, base_composite))
        decision_reason = "; ".join(reasons) if reasons else "Evaluated against candidate record"

        return CandidateScore(
            candidate_incident_id=candidate.id,
            combined_score=combined_score,
            exact_match_signal=exact_match,
            geographic_distance_m=geo_dist,
            geographic_score=geo_score,
            visual_similarity_score=vis_score,
            perceptual_similarity_score=phash_score,
            category_score=cat_score,
            text_score=text_score,
            decision_reason=decision_reason,
        )

    def _classify_decision(
        self,
        top_candidate: CandidateScore,
        runner_up: Optional[CandidateScore],
        location_conflict: bool,
    ) -> str:
        """Classifies matching outcome with separation analysis and conflict checking."""
        if location_conflict:
            return "NEEDS_HUMAN_CONFIRMATION"

        # Separation analysis
        separation = (top_candidate.combined_score - runner_up.combined_score) if runner_up else 1.0

        # Close competition between top candidates triggers human review
        if runner_up and separation < 0.10 and top_candidate.combined_score >= 0.50:
            return "NEEDS_HUMAN_CONFIRMATION"

        # High confidence match requires corroborating visual evidence or exact SHA-256 match.
        # Strict Rule: NEVER merge or declare likely existing incident on GPS distance alone!
        has_visual_support = (
            top_candidate.exact_match_signal or
            (top_candidate.perceptual_similarity_score is not None and top_candidate.perceptual_similarity_score >= 0.80) or
            (top_candidate.visual_similarity_score is not None and top_candidate.visual_similarity_score >= 0.75)
        )

        if top_candidate.combined_score >= 0.80 and top_candidate.category_score >= 0.70 and has_visual_support:
            if top_candidate.geographic_distance_m is None or top_candidate.geographic_distance_m <= 30.0:
                return "LIKELY_EXISTING_INCIDENT"

        # Moderate confidence or ambiguous score (including close GPS without visual match)
        if top_candidate.combined_score >= 0.50:
            return "NEEDS_HUMAN_CONFIRMATION"

        # Low confidence match -> new incident
        return "NEW_INCIDENT"

    @staticmethod
    def _compute_text_similarity(desc1: Optional[str], desc2: Optional[str]) -> Optional[float]:
        """Token Jaccard overlap on normalized non-stop words."""
        if not desc1 or not desc2:
            return None
        words1 = {w.lower().strip(".,!?\"'") for w in desc1.split() if len(w) > 3}
        words2 = {w.lower().strip(".,!?\"'") for w in desc2.split() if len(w) > 3}
        if not words1 or not words2:
            return None
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return round(intersection / union, 4) if union > 0 else 0.0

    def _get_item_assets_and_embeddings(
        self, db: Session, item: ReportItem
    ) -> Tuple[List[EvidenceAsset], List[List[float]]]:
        """Fetches evidence assets and defect crop embeddings for a report item."""
        rep_evs = db.query(ReportEvidence).filter(
            (ReportEvidence.report_item_id == item.id) |
            (ReportEvidence.report_id == item.report_id)
        ).all()

        asset_ids = [re.evidence_asset_id for re in rep_evs if re.evidence_asset_id]
        assets = db.query(EvidenceAsset).filter(EvidenceAsset.id.in_(asset_ids)).all() if asset_ids else []

        # Get embeddings
        embeddings = []
        embed_records = db.query(DetectionEmbedding).filter(
            DetectionEmbedding.evidence_asset_id.in_(asset_ids)
        ).all() if asset_ids else []

        for emb in embed_records:
            if emb.embedding_vector and isinstance(emb.embedding_vector, list):
                embeddings.append(emb.embedding_vector)

        return assets, embeddings

    def _get_incident_assets(self, db: Optional[Session], incident_id: str) -> List[EvidenceAsset]:
        """Fetches evidence assets linked to an incident via observations."""
        if db is None:
            return []
        obs = db.query(IncidentObservation).filter_by(incident_id=incident_id).all()
        asset_ids = [o.evidence_asset_id for o in obs if o.evidence_asset_id]
        if not asset_ids:
            return []
        return db.query(EvidenceAsset).filter(EvidenceAsset.id.in_(asset_ids)).all()

    def _get_incident_embeddings(self, db: Optional[Session], incident_id: str) -> List[List[float]]:
        """Fetches defect crop embeddings linked to an incident via observations."""
        if db is None:
            return []
        obs = db.query(IncidentObservation).filter_by(incident_id=incident_id).all()
        det_ids = [o.detection_id for o in obs if o.detection_id]
        if not det_ids:
            return []
        embed_records = db.query(DetectionEmbedding).filter(
            DetectionEmbedding.detection_id.in_(det_ids)
        ).all()
        return [r.embedding_vector for r in embed_records if r.embedding_vector and isinstance(r.embedding_vector, list)]
