"""
CivicLens Step 5 — Unit and Integration Tests for AI Defect Detection
====================================================================
Validates:
- Image validation (valid JPEG/PNG, unsupported formats, corruption, dimensions, EXIF transpose)
- Preprocessing and coordinate inverse transformation
- ModelProvider strategy pattern, hardware selection, and missing weights handling
- Multi-object defect detection (multiple distinct potholes preserved)
- Non-Maximum Suppression (overlapping duplicates merged, distinct defects preserved)
- Normalized coordinates [0.0, 1.0] and pixel bounding box mappings
- Database persistence of DetectionRun and Detection entities
"""

import io
import os
import pytest
from PIL import Image

from backend.db.engine import get_session_factory
from backend.db.models import (
    User, CitizenReport, ReportItem, EvidenceAsset, ReportEvidence,
    DetectionRun, Detection
)
from backend.services.image_validation_service import ImageValidationService
from backend.services.image_preprocessing_service import ImagePreprocessingService
from backend.services.model_provider import (
    BaseModelProvider, YoloModelProvider, MockModelProvider,
    RawPrediction, ModelWeightsMissingError
)
from backend.services.detection_postprocessing_service import DetectionPostprocessingService
from backend.services.detection_repository import DetectionRepository
from backend.services.defect_detection_service import DefectDetectionService


# ─── 1. Image Validation Tests ──────────────────────────────────────────

def test_validate_valid_jpeg():
    """Valid JPEG images are accepted and loaded into RGB PIL images."""
    val_svc = ImageValidationService()
    buf = io.BytesIO()
    img = Image.new("RGB", (640, 480), color=(120, 120, 120))
    img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    res = val_svc.validate_and_load(raw_bytes)
    assert res.is_valid is True
    assert res.width == 640
    assert res.height == 480
    assert res.image_format in ("JPEG", "JPG")
    assert res.image is not None


def test_validate_valid_png():
    """Valid PNG images are accepted and converted to RGB mode."""
    val_svc = ImageValidationService()
    buf = io.BytesIO()
    img = Image.new("RGBA", (800, 600), color=(50, 100, 150, 255))
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    res = val_svc.validate_and_load(raw_bytes)
    assert res.is_valid is True
    assert res.width == 800
    assert res.height == 600
    assert res.image.mode == "RGB"


def test_validate_unsupported_format():
    """Unsupported image formats (like GIF or arbitrary files) are safely rejected."""
    val_svc = ImageValidationService()
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    img.save(buf, format="GIF")
    raw_bytes = buf.getvalue()

    res = val_svc.validate_and_load(raw_bytes)
    assert res.is_valid is False
    assert res.error_code == "UNSUPPORTED_FORMAT"


def test_validate_corrupted_image():
    """Corrupted binary data is safely caught without crashing the application."""
    val_svc = ImageValidationService()
    corrupted_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00RandomJunkNotAValidStream"

    res = val_svc.validate_and_load(corrupted_bytes)
    assert res.is_valid is False
    assert res.error_code == "CORRUPTED_IMAGE"


def test_validate_dimension_limits():
    """Images below min resolution (32px) or above max resolution (8192px) fail safely."""
    val_svc = ImageValidationService(min_dimension=32, max_dimension=4096)

    # Too small
    buf_small = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buf_small, format="JPEG")
    res_small = val_svc.validate_and_load(buf_small.getvalue())
    assert res_small.is_valid is False
    assert res_small.error_code == "IMAGE_TOO_SMALL"

    # Too large
    val_tight = ImageValidationService(min_dimension=32, max_dimension=1000)
    buf_large = io.BytesIO()
    Image.new("RGB", (1200, 800)).save(buf_large, format="JPEG")
    res_large = val_tight.validate_and_load(buf_large.getvalue())
    assert res_large.is_valid is False
    assert res_large.error_code == "IMAGE_TOO_LARGE"


def test_validate_exif_orientation_normalization():
    """EXIF orientation tag is extracted and normalized via exif_transpose."""
    val_svc = ImageValidationService()
    buf = io.BytesIO()
    img = Image.new("RGB", (300, 200), color=(200, 50, 50))
    # Add EXIF orientation tag 6 (274 = 0x0112)
    exif = img.getexif()
    exif[0x0112] = 6  # Rotated 90 CW in camera
    img.save(buf, format="JPEG", exif=exif)

    res = val_svc.validate_and_load(buf.getvalue())
    assert res.is_valid is True
    # Transposed 90 degrees rotates 300x200 -> 200x300
    assert res.width == 200
    assert res.height == 300
    assert res.exif_transposed is True


# ─── 2. Image Preprocessing & Coordinate Transformation ─────────────────

def test_preprocessing_letterbox_and_inverse_box():
    """Letterbox scaling scales image and correctly maps bounding boxes back to original space."""
    prep = ImagePreprocessingService(target_size=640)
    orig_img = Image.new("RGB", (1280, 720), color=(30, 30, 30))

    preprocessed = prep.preprocess(orig_img)
    assert preprocessed.target_width == 640
    assert preprocessed.target_height == 640
    # Scale: 640 / 1280 = 0.5; new_h = 360; pad_y = (640 - 360) // 2 = 140
    assert preprocessed.scale == 0.5
    assert preprocessed.pad_x == 0
    assert preprocessed.pad_y == 140

    # Test coordinate mapping: box in center of 640x640 preprocessed space
    # In target: x1=100, y1=240, x2=200, y2=340
    x, y, w, h = prep.inverse_transform_box((100.0, 240.0, 200.0, 340.0), preprocessed)
    # x1: 100 / 0.5 = 200
    # y1: (240 - 140) / 0.5 = 200
    # x2: 200 / 0.5 = 400
    # y2: (340 - 140) / 0.5 = 400
    # w: 200, h: 200
    assert x == 200
    assert y == 200
    assert w == 200
    assert h == 200


# ─── 3. Model Provider Tests ────────────────────────────────────────────

def test_yolo_model_provider_missing_weights():
    """When weights are not found on disk, YoloModelProvider reports unavailable and raises safely."""
    provider = YoloModelProvider(weights_path="/tmp/nonexistent_yolo_weights.pt")
    assert provider.is_available() is False

    with pytest.raises(ModelWeightsMissingError, match="Model weights file not found"):
        provider.predict(Image.new("RGB", (100, 100)))


def test_mock_model_provider():
    """MockModelProvider returns deterministic predictions for tests."""
    canned = [
        RawPrediction(class_name="pothole", confidence=0.88, box_xyxy=(50.0, 50.0, 150.0, 150.0)),
        RawPrediction(class_name="road_damage", confidence=0.65, box_xyxy=(200.0, 200.0, 300.0, 300.0)),
    ]
    provider = MockModelProvider(canned_predictions=canned)
    assert provider.is_available() is True
    assert provider.supported_classes == ["pothole", "road_damage"]

    preds = provider.predict(Image.new("RGB", (640, 480)), conf_threshold=0.50)
    assert len(preds) == 2

    # Higher threshold filters out 0.65
    preds_high = provider.predict(Image.new("RGB", (640, 480)), conf_threshold=0.80)
    assert len(preds_high) == 1
    assert preds_high[0].class_name == "pothole"


# ─── 4. Multi-Object Detection & NMS Post-Processing ────────────────────

def test_multi_object_detection_preserves_three_distinct_potholes():
    """
    CRITICAL REQUIREMENT:
    When an image contains multiple distinct potholes (Pothole A, B, C),
    all three must be retained as separate detections with individual coordinates.
    """
    post_svc = DetectionPostprocessingService(iou_threshold=0.45, min_confidence=0.40)

    # 3 distinct non-overlapping potholes across a 1000x800 image
    pothole_a = RawPrediction(class_name="pothole", confidence=0.92, box_xyxy=(50.0, 50.0, 150.0, 150.0))
    pothole_b = RawPrediction(class_name="pothole", confidence=0.85, box_xyxy=(300.0, 100.0, 450.0, 250.0))
    pothole_c = RawPrediction(class_name="pothole", confidence=0.78, box_xyxy=(600.0, 400.0, 800.0, 600.0))

    results = post_svc.postprocess(
        predictions=[pothole_a, pothole_b, pothole_c],
        image_width=1000,
        image_height=800,
    )

    assert len(results) == 3
    # Verify each has its own independent bounding box
    assert results[0].bbox_x == 50
    assert results[0].bbox_w == 100
    assert results[0].normalized_xmin == 0.05
    assert results[0].normalized_xmax == 0.15

    assert results[1].bbox_x == 300
    assert results[1].bbox_w == 150
    assert results[1].normalized_xmin == 0.30

    assert results[2].bbox_x == 600
    assert results[2].bbox_w == 200
    assert results[2].normalized_xmin == 0.60

    # All three are high confidence (>= 0.75)
    for r in results:
        assert r.confidence_tier == "high"


def test_nms_merges_overlapping_duplicates_same_defect():
    """
    Non-Maximum Suppression merges two heavily overlapping candidate boxes of the
    same physical defect into the higher confidence prediction.
    """
    post_svc = DetectionPostprocessingService(iou_threshold=0.45)

    # Same pothole detected twice with high overlap (IoU > 0.8)
    box_high_conf = RawPrediction(class_name="pothole", confidence=0.91, box_xyxy=(100.0, 100.0, 200.0, 200.0))
    box_low_conf = RawPrediction(class_name="pothole", confidence=0.72, box_xyxy=(105.0, 102.0, 202.0, 198.0))

    results = post_svc.postprocess([box_high_conf, box_low_conf], image_width=800, image_height=600)

    assert len(results) == 1
    assert results[0].confidence == 0.91
    assert results[0].bbox_x == 100


def test_confidence_tiering_and_severity():
    """Detections are properly classified into high, medium, and low confidence tiers."""
    post_svc = DetectionPostprocessingService(min_confidence=0.40, high_confidence_threshold=0.75)

    high = RawPrediction(class_name="pothole", confidence=0.88, box_xyxy=(10.0, 10.0, 50.0, 50.0))
    med = RawPrediction(class_name="pothole", confidence=0.58, box_xyxy=(100.0, 100.0, 180.0, 180.0))
    low = RawPrediction(class_name="road_damage", confidence=0.35, box_xyxy=(300.0, 300.0, 380.0, 380.0))

    results = post_svc.postprocess([high, med, low], image_width=1000, image_height=1000)

    assert len(results) == 3
    tiers = {r.confidence: r.confidence_tier for r in results}
    assert tiers[0.88] == "high"
    assert tiers[0.58] == "medium"
    assert tiers[0.35] == "low"


# ─── 5. Database Persistence & Repository Tests ─────────────────────────

def test_detection_repository_crud():
    """DetectionRepository creates runs, saves multiple detections, and tracks metrics."""
    factory = get_session_factory()
    repo = DetectionRepository(session_factory=factory)

    # Create real user and evidence asset to satisfy foreign-key constraints
    db = factory()
    test_uid = f"test-reviewer-{os.urandom(4).hex()}"
    test_user = User(
        id=test_uid,
        display_name="Detection Reviewer Test",
        email=f"reviewer_{os.urandom(4).hex()}@bbmp.gov.in",
        password_hash="testhash123",
        role="municipal_officer",
    )
    asset_id = f"test-asset-{os.urandom(4).hex()}"
    asset = EvidenceAsset(
        id=asset_id,
        storage_key="/tmp/test_image.jpg",
        media_type="image/jpeg",
        content_sha256=os.urandom(16).hex(),
    )
    db.add(test_user)
    db.add(asset)
    db.commit()
    db.close()

    run_id = None
    det_ids = []
    try:
        # 1. Create run
        run_id = repo.create_run(
            evidence_asset_id=asset_id,
            model_name="yolov8-test",
            model_version="v1.0.0-test",
        )
        assert run_id is not None

        run_data = repo.get_run(run_id)
        assert run_data["processing_status"] == "running"

        # 2. Save 2 distinct detections
        post_svc = DetectionPostprocessingService()
        preds = post_svc.postprocess(
            [
                RawPrediction(class_name="pothole", confidence=0.89, box_xyxy=(20.0, 20.0, 100.0, 100.0)),
                RawPrediction(class_name="pothole", confidence=0.79, box_xyxy=(200.0, 200.0, 350.0, 350.0)),
            ],
            image_width=1000,
            image_height=800,
        )
        det_ids = repo.save_detections(
            run_id=run_id,
            evidence_asset_id=asset_id,
            detections=preds,
            model_version="v1.0.0-test",
        )
        assert len(det_ids) == 2

        # 3. Update run completed
        repo.update_run_status(run_id, status="completed", duration_ms=145.2)
        updated_run = repo.get_run(run_id)
        assert updated_run["processing_status"] == "completed"
        assert updated_run["processing_duration_ms"] == 145.2

        # 4. Fetch detections for run
        dets = repo.get_detections_for_run(run_id)
        assert len(dets) == 2
        assert dets[0]["category"] == "pothole"
        assert dets[0]["normalized_bbox"]["xmin"] == 0.02

        # 5. Review feedback update
        first_det_id = det_ids[0]
        reviewed = repo.update_detection_review(
            detection_id=first_det_id,
            review_status="confirmed",
            reviewed_by=test_uid,
            review_notes="Accurate pothole detection",
        )
        assert reviewed["review_status"] == "confirmed"
        assert reviewed["review_notes"] == "Accurate pothole detection"
    finally:
        # Clean up test rows to prevent database pollution
        cleanup_db = factory()
        try:
            if det_ids:
                cleanup_db.query(Detection).filter(Detection.id.in_(det_ids)).delete(synchronize_session=False)
            if run_id:
                cleanup_db.query(DetectionRun).filter_by(id=run_id).delete(synchronize_session=False)
            cleanup_db.query(EvidenceAsset).filter_by(id=asset_id).delete(synchronize_session=False)
            cleanup_db.query(User).filter_by(id=test_uid).delete(synchronize_session=False)
            cleanup_db.commit()
        except Exception:
            cleanup_db.rollback()
        finally:
            cleanup_db.close()
