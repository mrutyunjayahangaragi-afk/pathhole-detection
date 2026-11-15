"""
Location and Geocoding Service
==============================

Handles distance calculations (Haversine) and thread-safe reverse-geocoding
using OpenStreetMap Nominatim with rate-limiting, language support (en/kn),
and in-memory/fallback caching.
"""

from math import radians, sin, cos, sqrt, atan2
import threading
import time
from typing import Dict, Tuple, Optional
import requests

from backend.config import get_config
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


class LocationService:
    """Thread-safe location and reverse-geocoding service."""

    def __init__(self, config=None):
        self.config = config or get_config()
        self._lock = threading.Lock()
        self._last_request_time = 0.0
        self._cache: Dict[Tuple[float, float, str], str] = {}

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Returns distance in meters between two coordinates."""
        return haversine_distance_m(lat1, lon1, lat2, lon2)

    def is_within_radius(
        self, lat1: float, lon1: float, lat2: float, lon2: float, radius_m: Optional[float] = None
    ) -> bool:
        """Checks if two coordinates are within a specified distance threshold."""
        threshold = radius_m if radius_m is not None else self.config.DEDUP_RADIUS_METERS
        return self.calculate_distance(lat1, lon1, lat2, lon2) <= threshold

    def reverse_geocode(self, lat: float, lon: float, language: str = "en") -> str:
        """
        Reverse-geocodes (lat, lon) into a human-readable address.
        Guarantees thread-safe rate-limiting and falls back cleanly if unreachable.
        """
        cache_key = (round(lat, 5), round(lon, 5), language.lower())
        
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

            # Enforce minimum interval between external Nominatim API calls
            elapsed = time.time() - self._last_request_time
            min_interval = self.config.NOMINATIM_RATE_LIMIT_SECONDS
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

            self._last_request_time = time.time()

        # Perform network call outside lock to prevent blocking callers
        headers = {
            "User-Agent": self.config.NOMINATIM_USER_AGENT,
            "Accept-Language": "kn,en;q=0.8" if language == "kn" else "en,kn;q=0.5",
        }
        fallback = f"{lat:.5f}, {lon:.5f}"

        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"lat": lat, "lon": lon, "format": "json", "zoom": 17},
                headers=headers,
                timeout=3.0,
            )
            resp.raise_for_status()
            data = resp.json()
            address = data.get("display_name", fallback)
            # Shorten to municipal/district friendly string (first 3 parts)
            short_address = ", ".join(address.split(",")[:3]).strip()
            
            with self._lock:
                self._cache[cache_key] = short_address
            return short_address
        except Exception as e:
            logger.debug(f"Reverse geocode lookup failed for ({lat}, {lon}): {e}. Using fallback.")
            with self._lock:
                self._cache[cache_key] = fallback
            return fallback
