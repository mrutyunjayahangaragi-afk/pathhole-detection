"""
Location and Geocoding Service (Backward-Compatible Wrapper)
============================================================
Delegates to LocationIntelligenceService while preserving existing interfaces.
"""

from backend.services.location_intelligence_service import (
    LocationIntelligenceService, haversine_distance_m, StructuredAddress
)

# Re-export for compatibility
LocationService = LocationIntelligenceService
