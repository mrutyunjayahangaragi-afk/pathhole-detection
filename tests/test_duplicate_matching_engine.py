"""
Tests for Duplicate Matching Engine Components
==============================================
Tests defect crop extraction, visual embedding cosine similarity,
multi-signal scoring, category compatibility, and separation analysis.
"""

from PIL import Image, ImageDraw
from backend.services.defect_crop_service import DefectCropService
from backend.services.visual_embedding_service import VisualEmbeddingService, MockEmbeddingProvider
from backend.services.multi_signal_scoring_service import MultiSignalScoringService, CandidateScore


def test_defect_crop_service_coordinates_and_padding():
    img = Image.new("RGB", (500, 400), color=(100, 100, 100))
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 100, 200, 200], fill=(20, 20, 20))

    # Absolute pixel bbox crop
    crop_abs = DefectCropService.crop_defect(img, bbox=(100, 100, 100, 100), padding_percent=0.0)
    assert crop_abs.size == (100, 100)

    # Normalized bbox crop (xmin=0.2, ymin=0.25, xmax=0.4, ymax=0.5)
    crop_norm = DefectCropService.crop_defect(img, normalized_bbox=(0.2, 0.25, 0.4, 0.5), padding_percent=0.0)
    assert crop_norm.size == (100, 100)


def test_visual_embedding_cosine_similarity():
    service = VisualEmbeddingService(MockEmbeddingProvider(dimension=64))

    img1 = Image.new("RGB", (100, 100), color=(50, 50, 50))
    img2 = Image.new("RGB", (100, 100), color=(55, 55, 55))
    img_diff = Image.new("RGB", (100, 100), color=(240, 240, 240))

    v1 = service.get_crop_embedding(img1)
    v2 = service.get_crop_embedding(img2)
    v_diff = service.get_crop_embedding(img_diff)

    assert len(v1) == 64
    sim_identical = service.cosine_similarity(v1, v1)
    assert sim_identical == 1.0

    sim_similar = service.cosine_similarity(v1, v2)
    assert sim_similar >= 0.95

    sim_different = service.cosine_similarity(v1, v_diff)
    assert sim_different < sim_similar


def test_multi_signal_separation_and_classification():
    scoring = MultiSignalScoringService()

    # High confidence candidate with no close competitor -> LIKELY_EXISTING_INCIDENT
    cand_high = CandidateScore(
        candidate_incident_id="inc-1",
        combined_score=0.88,
        exact_match_signal=False,
        geographic_distance_m=4.2,
        geographic_score=0.96,
        visual_similarity_score=0.85,
        perceptual_similarity_score=0.80,
        category_score=1.0,
        text_score=0.6,
        decision_reason="Strong match across signals",
    )
    dec1 = scoring._classify_decision(top_candidate=cand_high, runner_up=None, location_conflict=False)
    assert dec1 == "LIKELY_EXISTING_INCIDENT"

    # Close competition between two candidates (|Δ| < 0.10) -> NEEDS_HUMAN_CONFIRMATION
    cand_comp = CandidateScore(
        candidate_incident_id="inc-2",
        combined_score=0.83,
        exact_match_signal=False,
        geographic_distance_m=8.5,
        geographic_score=0.89,
        visual_similarity_score=0.82,
        perceptual_similarity_score=0.78,
        category_score=1.0,
        text_score=0.5,
        decision_reason="Competitor candidate",
    )
    dec2 = scoring._classify_decision(top_candidate=cand_high, runner_up=cand_comp, location_conflict=False)
    assert dec2 == "NEEDS_HUMAN_CONFIRMATION"

    # Conflicting GPS location flag -> strictly NEEDS_HUMAN_CONFIRMATION
    dec_conflict = scoring._classify_decision(top_candidate=cand_high, runner_up=None, location_conflict=True)
    assert dec_conflict == "NEEDS_HUMAN_CONFIRMATION"

    # Low score -> NEW_INCIDENT
    cand_low = CandidateScore(
        candidate_incident_id="inc-3",
        combined_score=0.38,
        exact_match_signal=False,
        geographic_distance_m=120.0,
        geographic_score=0.0,
        visual_similarity_score=0.45,
        perceptual_similarity_score=0.40,
        category_score=0.7,
        text_score=0.1,
        decision_reason="Far distance, weak appearance match",
    )
    dec3 = scoring._classify_decision(top_candidate=cand_low, runner_up=None, location_conflict=False)
    assert dec3 == "NEW_INCIDENT"
