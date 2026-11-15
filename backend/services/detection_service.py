"""
Detection Service
=================

Manages AI defect detection outputs, bounding boxes, severity estimations,
and links them to evidence media assets.
"""

from typing import List, Dict, Any, Optional
from backend.domain.models import Detection, SeverityLevel
from backend.errors import ValidationError


class DetectionService:
    """Handles defect detections within evidence media."""

    @staticmethod
    def create_detection_from_dict(
        data: Dict[str, Any], evidence_asset_id: Optional[str] = None
    ) -> Detection:
        """Parses and validates a single defect detection."""
        bbox = data.get("bbox", [0, 0, 0, 0])
        if len(bbox) != 4:
            raise ValidationError("Bounding box must contain exactly 4 integers [x, y, w, h]")

        try:
            severity = SeverityLevel.from_str(data.get("severity", "minor"))
        except ValueError as e:
            raise ValidationError(str(e)) from e

        return Detection(
            evidence_asset_id=evidence_asset_id,
            defect_type=data.get("defect_type", "pothole"),
            bbox_x=int(bbox[0]),
            bbox_y=int(bbox[1]),
            bbox_w=int(bbox[2]),
            bbox_h=int(bbox[3]),
            confidence=float(data.get("confidence", 0.0)),
            est_depth_cm=float(data.get("est_depth_cm", 0.0)),
            severity=severity,
            model_version=data.get("model_version", "yolov8-baseline"),
        )
