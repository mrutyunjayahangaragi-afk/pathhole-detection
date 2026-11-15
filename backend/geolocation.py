"""
Free geolocation helper.

Reverse-geocoding turning (lat, lon) into a human-readable address/road name
for the municipal dashboard using OpenStreetMap's Nominatim API.
Thread-safe rate-limiting and in-memory caching.
"""

import sys
from pathlib import Path
_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from typing import Optional
from backend.services.location_service import LocationService

_default_location_service = LocationService()


def reverse_geocode(lat: float, lon: float, language: str = "en") -> str:
    """
    Returns a short human-readable address for the given coordinates.
    Falls back cleanly to coordinate string if API is unreachable or rate-limited.
    """
    return _default_location_service.reverse_geocode(lat, lon, language=language)
