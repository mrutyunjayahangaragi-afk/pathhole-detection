"""
Duplicate Matching Service
==========================

Encapsulates candidate discovery and duplicate matching decisions.
In Step 2 (Foundation), this preserves the baseline spatial radius threshold (15m)
while outputting structured MatchDecision domain entities.
"""

from typing import Optional, List, Dict, Any
import sqlite3
from backend.config import get_config
from backend.database import get_db
from backend.domain.models import MatchDecision, MatchVerdict, CitizenReport, SeverityLevel
from backend.services.location_service import LocationService


class DuplicateMatchingService:
    """Evaluates incoming reports against existing incidents."""

    def __init__(self, location_service: Optional[LocationService] = None, config=None):
        self.config = config or get_config()
        self.location_service = location_service or LocationService(self.config)

    def evaluate_report_against_existing(
        self, conn: sqlite3.Connection, lat: float, lon: float, report_id: str = ""
    ) -> MatchDecision:
        """
        Evaluates coordinates against existing unrepaired detections/incidents
        using the baseline radius rule. Returns a structured MatchDecision.
        """
        # Query unrepaired open records from detections
        rows = conn.execute(
            "SELECT id, latitude, longitude, severity, est_depth_cm, report_count "
            "FROM detections WHERE status != 'repaired'"
        ).fetchall()

        closest_id = None
        min_distance = float("inf")
        radius = self.config.DEDUP_RADIUS_METERS

        for row in rows:
            dist = self.location_service.calculate_distance(
                lat, lon, row["latitude"], row["longitude"]
            )
            if dist <= radius and dist < min_distance:
                min_distance = dist
                closest_id = row["id"]

        if closest_id is not None:
            # Baseline treats <= 15m as a match
            confidence = max(0.5, 1.0 - (min_distance / radius))
            verdict = MatchVerdict.EXACT_DUPLICATE if min_distance <= (radius * 0.7) else MatchVerdict.PROBABLE_MATCH
            return MatchDecision(
                report_id=report_id,
                candidate_incident_id=closest_id,
                verdict=verdict,
                confidence_score=round(confidence, 2),
                spatial_distance_m=round(min_distance, 2),
                reason=f"Found existing open incident within {min_distance:.1f}m (threshold {radius}m)",
            )

        return MatchDecision(
            report_id=report_id,
            candidate_incident_id=None,
            verdict=MatchVerdict.DISTINCT_INCIDENT,
            confidence_score=1.0,
            spatial_distance_m=0.0,
            reason=f"No existing incident within {radius}m radius.",
        )
