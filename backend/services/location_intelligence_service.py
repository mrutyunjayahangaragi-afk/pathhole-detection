"""
Location Intelligence Service
=============================
Provides validated coordinate verification, thread-safe Nominatim-compliant
reverse geocoding, structured address decomposition without fabrication,
and PostGIS / Haversine spatial analysis.
"""

from math import radians, sin, cos, sqrt, atan2
import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional, Any
import requests

from backend.config import get_config
from backend.db.engine import get_session_factory
from backend.db.models import LocationRecord
from backend.errors import ValidationError
from backend.logging_config import setup_logging

logger = setup_logging()

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two (lat, lon) coordinates in meters."""
    r_earth = 6371000.0  # Earth radius in meters
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2.0) ** 2
    return 2.0 * r_earth * atan2(sqrt(a), sqrt(1.0 - a))


@dataclass
class StructuredAddress:
    display_name: str
    road_name: Optional[str]
    road_type: Optional[str]
    locality: Optional[str]
    suburb: Optional[str]
    city: Optional[str]
    district: Optional[str]
    state: Optional[str]
    postal_code: Optional[str]
    country: Optional[str]
    raw_json: Optional[str]
    status: str  # 'completed', 'cached', 'failed', 'skipped'
    provider: str = "nominatim"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "display_name": self.display_name,
            "road_name": self.road_name,
            "road_type": self.road_type,
            "locality": self.locality,
            "suburb": self.suburb,
            "city": self.city,
            "district": self.district,
            "state": self.state,
            "postal_code": self.postal_code,
            "country": self.country,
            "status": self.status,
            "provider": self.provider,
        }


class LocationIntelligenceService:
    """Centralized, Nominatim-compliant location and spatial intelligence engine."""

    def __init__(self, config=None, session_factory=None):
        self.config = config or get_config()
        self._custom_session_factory = session_factory
        self._lock = threading.Lock()
        self._last_request_time = 0.0
        self._cache: Dict[Tuple[float, float, str], StructuredAddress] = {}

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    @staticmethod
    def validate_coordinates(lat: Any, lon: Any) -> Tuple[float, float]:
        """Validates that latitude and longitude are valid floats within bounds."""
        try:
            flat = float(lat)
            flon = float(lon)
        except (ValueError, TypeError):
            raise ValidationError("Latitude and longitude must be valid floating-point numbers.")

        if not (-90.0 <= flat <= 90.0):
            raise ValidationError(f"Latitude {flat} is outside valid range [-90.0, 90.0].")
        if not (-180.0 <= flon <= 180.0):
            raise ValidationError(f"Longitude {flon} is outside valid range [-180.0, 180.0].")

        return flat, flon

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Returns distance in meters between two coordinates."""
        return haversine_distance_m(lat1, lon1, lat2, lon2)

    def is_within_radius(
        self, lat1: float, lon1: float, lat2: float, lon2: float, radius_m: Optional[float] = None
    ) -> bool:
        """Checks if two coordinates are within a specified distance threshold."""
        threshold = radius_m if radius_m is not None else getattr(self.config, "DEDUP_RADIUS_METERS", 50.0)
        return self.calculate_distance(lat1, lon1, lat2, lon2) <= threshold

    def reverse_geocode_structured(
        self, lat: float, lon: float, language: str = "en"
    ) -> StructuredAddress:
        """
        Reverse-geocodes (lat, lon) into structured address components.
        Respects Nominatim rate-limiting, thread-safe memory caching, and timeout policies.
        Never hallucinates missing address components (they remain None).
        """
        flat, flon = self.validate_coordinates(lat, lon)
        cache_key = (round(flat, 5), round(flon, 5), language.lower())

        with self._lock:
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                return StructuredAddress(
                    display_name=cached.display_name,
                    road_name=cached.road_name,
                    road_type=cached.road_type,
                    locality=cached.locality,
                    suburb=cached.suburb,
                    city=cached.city,
                    district=cached.district,
                    state=cached.state,
                    postal_code=cached.postal_code,
                    country=cached.country,
                    raw_json=cached.raw_json,
                    status="cached",
                    provider=cached.provider,
                )

            # Enforce 1.0s minimum interval between Nominatim API calls
            elapsed = time.time() - self._last_request_time
            min_interval = getattr(self.config, "NOMINATIM_RATE_LIMIT_SECONDS", 1.0)
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

            self._last_request_time = time.time()

        user_agent = getattr(
            self.config, "NOMINATIM_USER_AGENT", "CivicLens-Infrastructure-Triage/2.0 (civiclens-bbmp@civiclens.org)"
        )
        headers = {
            "User-Agent": user_agent,
            "Accept-Language": "kn,en;q=0.8" if language == "kn" else "en,kn;q=0.5",
        }
        fallback_display = f"{flat:.5f}, {flon:.5f}"

        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"lat": flat, "lon": flon, "format": "jsonv2", "addressdetails": 1, "zoom": 18},
                headers=headers,
                timeout=3.0,
            )
            resp.raise_for_status()
            data = resp.json()

            addr = data.get("address", {})
            road = addr.get("road") or addr.get("pedestrian") or addr.get("footway") or addr.get("cycleway") or addr.get("street")
            road_type = data.get("type") or addr.get("highway")
            locality = addr.get("neighbourhood") or addr.get("suburb") or addr.get("quarter")
            suburb = addr.get("suburb")
            city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality")
            district = addr.get("state_district") or addr.get("county") or addr.get("district")
            state = addr.get("state")
            postal_code = addr.get("postcode")
            country = addr.get("country")
            display = data.get("display_name", fallback_display)

            res = StructuredAddress(
                display_name=display,
                road_name=road,
                road_type=road_type,
                locality=locality,
                suburb=suburb,
                city=city,
                district=district,
                state=state,
                postal_code=postal_code,
                country=country,
                raw_json=json.dumps(data),
                status="completed",
                provider="nominatim",
            )

            with self._lock:
                self._cache[cache_key] = res
            return res

        except Exception as e:
            logger.debug(f"Nominatim lookup failed for ({flat}, {flon}): {e}. Using coordinate fallback.")
            fail_res = StructuredAddress(
                display_name=fallback_display,
                road_name=None,
                road_type=None,
                locality=None,
                suburb=None,
                city=None,
                district=None,
                state=None,
                postal_code=None,
                country=None,
                raw_json=None,
                status="failed",
                provider="nominatim",
            )
            with self._lock:
                self._cache[cache_key] = fail_res
            return fail_res

    def reverse_geocode(self, lat: float, lon: float, language: str = "en") -> str:
        """Compatibility wrapper returning formatted address string."""
        struct = self.reverse_geocode_structured(lat, lon, language)
        if struct.display_name and struct.status in ("completed", "cached"):
            parts = [p.strip() for p in struct.display_name.split(",") if p.strip()]
            return ", ".join(parts[:3]) if parts else struct.display_name
        return struct.display_name

    def process_and_persist_location(
        self,
        report_id: str,
        lat: float,
        lon: float,
        location_accuracy_m: Optional[float] = None,
        location_source: str = "manual_pin",
        language: str = "en",
    ) -> Optional[LocationRecord]:
        """
        Reverse-geocodes and safely saves structured location record to database.
        Never blocks report creation if geocoding fails.
        """
        flat, flon = self.validate_coordinates(lat, lon)
        source = location_source if location_source in ("device_gps", "manual_pin", "exif_gps", "citizen_text") else "manual_pin"

        struct = self.reverse_geocode_structured(flat, flon, language)
        now = datetime.now(timezone.utc)

        db = self._session_factory()
        try:
            # Check if record already exists for this report
            existing = db.query(LocationRecord).filter_by(report_id=report_id).first()
            if existing:
                rec = existing
                rec.latitude = flat
                rec.longitude = flon
                rec.location_accuracy_m = location_accuracy_m
                rec.location_source = source
                rec.road_name = struct.road_name
                rec.road_type = struct.road_type
                rec.locality = struct.locality
                rec.suburb = struct.suburb
                rec.city = struct.city
                rec.district = struct.district
                rec.state = struct.state
                rec.postal_code = struct.postal_code
                rec.country = struct.country
                rec.normalized_address = struct.display_name
                rec.raw_geocoding_json = struct.raw_json
                rec.geocoding_status = struct.status
                rec.geocoded_at = now
            else:
                rec = LocationRecord(
                    id=str(uuid.uuid4()),
                    report_id=report_id,
                    latitude=flat,
                    longitude=flon,
                    location_accuracy_m=location_accuracy_m,
                    location_source=source,
                    road_name=struct.road_name,
                    road_type=struct.road_type,
                    locality=struct.locality,
                    suburb=struct.suburb,
                    city=struct.city,
                    district=struct.district,
                    state=struct.state,
                    postal_code=struct.postal_code,
                    country=struct.country,
                    normalized_address=struct.display_name,
                    raw_geocoding_json=struct.raw_json,
                    geocoding_provider=struct.provider,
                    geocoding_status=struct.status,
                    geocoded_at=now,
                )
                db.add(rec)
            db.commit()
            return rec
        except Exception as e:
            logger.warning(f"Failed to persist LocationRecord for report {report_id}: {e}")
            db.rollback()
            return None
        finally:
            db.close()
