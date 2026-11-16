"""
Tests for Location Intelligence Service
=======================================
Verifies coordinate validation, structured reverse geocoding, Nominatim compliance,
caching, fallback handling, and persistence.
"""

import time
from unittest.mock import patch, MagicMock
import pytest

from backend.errors import ValidationError
from backend.services.location_intelligence_service import (
    LocationIntelligenceService, haversine_distance_m, StructuredAddress
)
from backend.db.engine import get_session_factory
from backend.db.models import CitizenReport, LocationRecord, User


def test_coordinate_validation():
    service = LocationIntelligenceService()

    # Valid coordinates
    lat, lon = service.validate_coordinates("12.9716", "77.5946")
    assert lat == 12.9716
    assert lon == 77.5946

    # Out of range latitude
    with pytest.raises(ValidationError):
        service.validate_coordinates(95.0, 77.5946)

    with pytest.raises(ValidationError):
        service.validate_coordinates(-91.0, 77.5946)

    # Out of range longitude
    with pytest.raises(ValidationError):
        service.validate_coordinates(12.9716, 185.0)

    # Non-numeric string
    with pytest.raises(ValidationError):
        service.validate_coordinates("not-a-number", "77.5946")


def test_haversine_distance_calculation():
    # MG Road to Indiranagar (approx 3.5 km)
    lat1, lon1 = 12.9756, 77.6066
    lat2, lon2 = 12.9784, 77.6408
    dist = haversine_distance_m(lat1, lon1, lat2, lon2)
    assert 3000 <= dist <= 4000


def test_structured_reverse_geocoding_success():
    service = LocationIntelligenceService()
    mock_payload = {
        "display_name": "100 Feet Road, HAL 2nd Stage, Indiranagar, Bengaluru, Bengaluru Urban, Karnataka, 560038, India",
        "type": "secondary",
        "address": {
            "road": "100 Feet Road",
            "highway": "secondary",
            "neighbourhood": "HAL 2nd Stage",
            "suburb": "Indiranagar",
            "city": "Bengaluru",
            "state_district": "Bengaluru Urban",
            "state": "Karnataka",
            "postcode": "560038",
            "country": "India",
        }
    }

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        res = service.reverse_geocode_structured(12.9716, 77.5946, language="en")
        assert res.status == "completed"
        assert res.road_name == "100 Feet Road"
        assert res.road_type == "secondary"
        assert res.locality == "HAL 2nd Stage"
        assert res.suburb == "Indiranagar"
        assert res.city == "Bengaluru"
        assert res.district == "Bengaluru Urban"
        assert res.state == "Karnataka"
        assert res.postal_code == "560038"
        assert res.country == "India"


def test_missing_address_components_remain_null():
    service = LocationIntelligenceService()
    # Payload with missing road, suburb, and district
    mock_payload = {
        "display_name": "Bengaluru, Karnataka, India",
        "type": "city",
        "address": {
            "city": "Bengaluru",
            "state": "Karnataka",
            "country": "India",
        }
    }

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        res = service.reverse_geocode_structured(12.9700, 77.5900, language="en")
        assert res.status == "completed"
        assert res.road_name is None  # Must remain NULL, not fabricated
        assert res.suburb is None
        assert res.district is None
        assert res.city == "Bengaluru"


def test_reverse_geocoding_fallback_on_failure():
    service = LocationIntelligenceService()

    with patch("requests.get", side_effect=Exception("Nominatim network timeout")):
        res = service.reverse_geocode_structured(12.9750, 77.5950, language="en")
        assert res.status == "failed"
        assert "12.97500, 77.59500" in res.display_name
        assert res.road_name is None


def test_nominatim_caching():
    service = LocationIntelligenceService()
    mock_payload = {
        "display_name": "Brigade Road, Bengaluru, India",
        "address": {"road": "Brigade Road", "city": "Bengaluru"}
    }

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_get.return_value = mock_resp

        res1 = service.reverse_geocode_structured(12.9720, 77.6080)
        assert res1.status == "completed"
        assert mock_get.call_count == 1

        # Second call to same coordinates should hit cache and NOT invoke requests.get
        res2 = service.reverse_geocode_structured(12.9720, 77.6080)
        assert res2.status == "cached"
        assert mock_get.call_count == 1
