"""
Report Ingestion Service
========================

Validates and processes incoming reports from vehicle telemetry and citizen
submissions, invoking duplicate evaluation and asynchronous reverse geocoding.
"""

from typing import Dict, Any, Optional, Tuple
import time
import uuid
import threading

from backend.config import get_config
from backend.database import get_db
from backend.domain.models import CitizenReport, SourceType, SeverityLevel
from backend.errors import ValidationError
from backend.services.duplicate_matching_service import DuplicateMatchingService
from backend.services.location_service import LocationService
from backend.logging_config import setup_logging

logger = setup_logging()


class ReportService:
    """Handles report ingestion, validation, and persistence."""

    def __init__(
        self,
        location_service: Optional[LocationService] = None,
        duplicate_matcher: Optional[DuplicateMatchingService] = None,
        db_path: Optional[str] = None,
    ):
        self.config = get_config()
        self.db_path = db_path
        self.location_service = location_service or LocationService(self.config)
        self.duplicate_matcher = duplicate_matcher or DuplicateMatchingService(
            self.location_service, self.config
        )

    def validate_payload(self, data: Dict[str, Any]) -> Tuple[float, float]:
        """Validates incoming detection payload fields."""
        required = ["vehicle_id", "latitude", "longitude", "severity"]
        missing = [f for f in required if f not in data or data[f] is None]
        if missing:
            raise ValidationError(f"Missing required fields: {missing}")

        allowed_severities = {"minor", "moderate", "severe"}
        if data["severity"] not in allowed_severities:
            raise ValidationError(f"severity must be one of {sorted(allowed_severities)}")

        try:
            lat = float(data["latitude"])
            lon = float(data["longitude"])
        except (TypeError, ValueError) as e:
            raise ValidationError("latitude/longitude must be numeric") from e

        if not (-90.0 <= lat <= 90.0):
            raise ValidationError(f"Latitude {lat} out of valid range [-90, 90]")
        if not (-180.0 <= lon <= 180.0):
            raise ValidationError(f"Longitude {lon} out of valid range [-180, 180]")

        return lat, lon

    def _async_geocode(self, detection_id: str, lat: float, lon: float) -> None:
        """Asynchronously reverse geocodes the coordinates and updates address."""
        def run():
            try:
                address = self.location_service.reverse_geocode(lat, lon)
                if address:
                    with get_db(self.db_path) as conn:
                        conn.execute(
                            "UPDATE detections SET address = ? WHERE id = ?",
                            (address, detection_id),
                        )
            except Exception as e:
                logger.error(f"Geocoding background thread failed for {detection_id}: {e}")

        threading.Thread(target=run, daemon=True).start()

    def process_detection_report(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        """
        Processes a detection report according to the baseline rules:
        - If nearby unrepaired detection found: merges into existing record
        - If no nearby detection: creates a new record
        Returns: (result_dict, http_status_code)
        """
        lat, lon = self.validate_payload(data)
        severity = data["severity"]
        est_depth_cm = float(data.get("est_depth_cm", 0.0) or 0.0)
        confidence = float(data.get("confidence", 0.0) or 0.0)
        image_ref = data.get("image_ref")
        vehicle_id = data["vehicle_id"]

        severity_rank = {"minor": 0, "moderate": 1, "severe": 2}
        now = time.time()

        with get_db(self.db_path) as conn:
            # Evaluate using duplicate matcher
            match = self.duplicate_matcher.evaluate_report_against_existing(conn, lat, lon)
            
            if match.candidate_incident_id is not None:
                existing_id = match.candidate_incident_id
                existing = conn.execute(
                    "SELECT * FROM detections WHERE id = ?", (existing_id,)
                ).fetchone()

                merged_severity = (
                    severity
                    if severity_rank[severity] > severity_rank[existing["severity"]]
                    else existing["severity"]
                )
                conn.execute(
                    """UPDATE detections
                       SET report_count = report_count + 1,
                           severity = ?,
                           est_depth_cm = MAX(est_depth_cm, ?),
                           timestamp = ?
                       WHERE id = ?""",
                    (merged_severity, est_depth_cm, now, existing_id),
                )
                row = conn.execute(
                    "SELECT * FROM detections WHERE id = ?", (existing_id,)
                ).fetchone()
                return {"merged": True, "detection": dict(row)}, 200

            # New detection
            new_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO detections
                   (id, vehicle_id, latitude, longitude, severity, est_depth_cm,
                    confidence, image_ref, timestamp, status, report_count, address)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'reported', 1, NULL)""",
                (new_id, vehicle_id, lat, lon, severity, est_depth_cm, confidence, image_ref, now),
            )
            row = conn.execute("SELECT * FROM detections WHERE id = ?", (new_id,)).fetchone()

        # Trigger async geocode for newly inserted records
        self._async_geocode(new_id, lat, lon)
        return {"merged": False, "detection": dict(row)}, 201
