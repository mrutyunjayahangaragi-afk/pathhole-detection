"""
Detection Postprocessing Service
================================
Refines raw model predictions into standardized domain defect detections:
- Non-Maximum Suppression (NMS) removes duplicate overlapping detections of the same defect
- Preserves distinct physical defects (even if close together) as separate entities
- Normalizes bounding box coordinates to [0.0, 1.0] relative to image dimensions
- Calculates absolute pixel coordinates [x, y, w, h]
- Computes confidence tiers (high: >= 0.75, medium: >= 0.40, low: < 0.40)
- Estimates surface severity level from relative box area
"""

from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional
from backend.services.model_provider import RawPrediction


@dataclass
class ProcessedDetection:
    """Standardized, post-processed defect detection output."""
    defect_category: str
    confidence: float
    confidence_tier: str       # "high" | "medium" | "low"
    bbox_x: int                # pixel x
    bbox_y: int                # pixel y
    bbox_w: int                # pixel width
    bbox_h: int                # pixel height
    normalized_xmin: float     # 0.0 to 1.0
    normalized_ymin: float     # 0.0 to 1.0
    normalized_xmax: float     # 0.0 to 1.0
    normalized_ymax: float     # 0.0 to 1.0
    image_width: int
    image_height: int
    est_depth_cm: float
    severity: str              # "minor" | "moderate" | "severe"
    review_status: str         # "unreviewed" | "uncertain"


class DetectionPostprocessingService:
    """Handles NMS deduplication, coordinate normalization, and confidence stratification."""

    def __init__(
        self,
        iou_threshold: float = 0.45,
        min_confidence: float = 0.40,
        high_confidence_threshold: float = 0.75,
    ):
        self.iou_threshold = iou_threshold
        self.min_confidence = min_confidence
        self.high_confidence_threshold = high_confidence_threshold

    @staticmethod
    def compute_iou(
        box_a: Tuple[float, float, float, float],
        box_b: Tuple[float, float, float, float],
    ) -> float:
        """
        Calculates Intersection-over-Union (IoU) between two bounding boxes [x1, y1, x2, y2].
        """
        xa1, ya1, xa2, ya2 = box_a
        xb1, yb1, xb2, yb2 = box_b

        # Determine intersection rectangle
        inter_x1 = max(xa1, xb1)
        inter_y1 = max(ya1, yb1)
        inter_x2 = min(xa2, xb2)
        inter_y2 = min(ya2, yb2)

        inter_w = max(0.0, inter_x2 - inter_x1)
        inter_h = max(0.0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        # Compute union
        area_a = max(0.0, xa2 - xa1) * max(0.0, ya2 - ya1)
        area_b = max(0.0, xb2 - xb1) * max(0.0, yb2 - yb1)
        union_area = area_a + area_b - inter_area

        if union_area <= 0.0:
            return 0.0

        return inter_area / union_area

    def apply_nms(
        self,
        predictions: List[RawPrediction],
    ) -> List[RawPrediction]:
        """
        Performs class-aware Non-Maximum Suppression to remove redundant overlapping boxes.
        Distinct objects (IoU <= iou_threshold) are kept strictly separate.
        """
        if not predictions:
            return []

        # Group predictions by class
        by_class: Dict[str, List[RawPrediction]] = {}
        for p in predictions:
            by_class.setdefault(p.class_name, []).append(p)

        retained: List[RawPrediction] = []

        for class_name, preds in by_class.items():
            # Sort by confidence descending
            sorted_preds = sorted(preds, key=lambda x: x.confidence, reverse=True)
            chosen: List[RawPrediction] = []

            for candidate in sorted_preds:
                should_keep = True
                for selected in chosen:
                    iou = self.compute_iou(candidate.box_xyxy, selected.box_xyxy)
                    if iou > self.iou_threshold:
                        # Overlapping redundant box of the same physical defect
                        should_keep = False
                        break

                if should_keep:
                    chosen.append(candidate)

            retained.extend(chosen)

        return retained

    def postprocess(
        self,
        predictions: List[RawPrediction],
        image_width: int,
        image_height: int,
    ) -> List[ProcessedDetection]:
        """
        Applies NMS, coordinate normalization, confidence tiering, and severity estimation.
        """
        if not predictions or image_width <= 0 or image_height <= 0:
            return []

        # 1. Non-Maximum Suppression
        nms_preds = self.apply_nms(predictions)

        results: List[ProcessedDetection] = []
        frame_area = image_width * image_height

        for p in nms_preds:
            x1, y1, x2, y2 = p.box_xyxy

            # Clamp coordinates to image boundaries
            cx1 = max(0.0, min(float(x1), float(image_width)))
            cy1 = max(0.0, min(float(y1), float(image_height)))
            cx2 = max(0.0, min(float(x2), float(image_width)))
            cy2 = max(0.0, min(float(y2), float(image_height)))

            # Absolute integer box [x, y, w, h]
            px = int(round(cx1))
            py = int(round(cy1))
            pw = int(round(max(0.0, cx2 - cx1)))
            ph = int(round(max(0.0, cy2 - cy1)))

            # Normalized coordinates [0.0, 1.0]
            norm_xmin = round(cx1 / image_width, 4)
            norm_ymin = round(cy1 / image_height, 4)
            norm_xmax = round(cx2 / image_width, 4)
            norm_ymax = round(cy2 / image_height, 4)

            # Confidence tiering
            conf = round(p.confidence, 4)
            if conf >= self.high_confidence_threshold:
                tier = "high"
                rev_status = "unreviewed"
            elif conf >= self.min_confidence:
                tier = "medium"
                rev_status = "uncertain"
            else:
                tier = "low"
                rev_status = "uncertain"

            # Severity heuristic based on relative surface area
            box_area = pw * ph
            area_ratio = box_area / max(frame_area, 1)

            depth_est = p.est_depth_cm or 0.0
            if depth_est >= 5.0 or area_ratio >= 0.04:
                sev = "severe"
            elif depth_est >= 2.5 or area_ratio >= 0.015:
                sev = "moderate"
            else:
                sev = "minor"

            results.append(
                ProcessedDetection(
                    defect_category=p.class_name,
                    confidence=conf,
                    confidence_tier=tier,
                    bbox_x=px,
                    bbox_y=py,
                    bbox_w=pw,
                    bbox_h=ph,
                    normalized_xmin=norm_xmin,
                    normalized_ymin=norm_ymin,
                    normalized_xmax=norm_xmax,
                    normalized_ymax=norm_ymax,
                    image_width=image_width,
                    image_height=image_height,
                    est_depth_cm=round(depth_est, 2),
                    severity=sev,
                    review_status=rev_status,
                )
            )

        return results
