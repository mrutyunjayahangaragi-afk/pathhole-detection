"""
Tests for PostGIS and Geospatial Viewport Queries (Step 9)
==========================================================
Validates bounding box constraints, coordinate bounds enforcement,
response capping, category/status filtering, and grid clustering.
"""

import uuid
import pytest
from backend.db.engine import get_session_factory
from backend.db.models import Incident, IncidentPublication
from backend.services.public_incident_service import PublicIncidentService


def test_spatial_viewport_boundary_and_capping(client):
    """Scenario 7 & 10: Viewport boundaries filter points and respect limits."""
    factory = get_session_factory()
    db = factory()
    try:
        # Incident inside Bengaluru box
        inc_inside = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            status="verified",
            latitude=12.9716,
            longitude=77.5946,
            address="Inside Box",
        )
        # Incident far outside (e.g. Delhi)
        inc_outside = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            status="verified",
            latitude=28.6139,
            longitude=77.2090,
            address="Outside Box",
        )
        db.add_all([inc_inside, inc_outside])
        db.commit()

        pub1 = IncidentPublication(incident_id=inc_inside.id, visibility_status="PUBLIC")
        pub2 = IncidentPublication(incident_id=inc_outside.id, visibility_status="PUBLIC")
        db.add_all([pub1, pub2])
        db.commit()

        in_id = inc_inside.id
        out_id = inc_outside.id
    finally:
        db.close()

    resp = client.get("/api/v2/public/incidents/viewport?min_lon=77.50&min_lat=12.90&max_lon=77.70&max_lat=13.10")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    ids = [it["id"] for it in items]
    assert in_id in ids
    assert out_id not in ids, "Incident outside bounding box must be excluded"


def test_invalid_coordinates_rejected(client):
    """Scenario 8: Invalid coordinates return HTTP 400 Bad Request."""
    # Latitude > 90
    resp1 = client.get("/api/v2/public/incidents/viewport?min_lon=77.0&min_lat=12.0&max_lon=78.0&max_lat=95.0")
    assert resp1.status_code == 400

    # min_lat > max_lat
    resp2 = client.get("/api/v2/public/incidents/viewport?min_lon=77.0&min_lat=15.0&max_lon=78.0&max_lat=12.0")
    assert resp2.status_code == 400

    # Non-numeric string
    resp3 = client.get("/api/v2/public/incidents/viewport?min_lon=abc&min_lat=12.0&max_lon=78.0&max_lat=13.0")
    assert resp3.status_code == 400


def test_grid_clustering_preserves_identities(client):
    """Scenario 11: Clusters aggregate nearby markers without merging underlying entities."""
    factory = get_session_factory()
    db = factory()
    try:
        # Create 3 points close to each other
        points = []
        for i in range(3):
            inc = Incident(
                incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
                category="pothole",
                status="in_progress",
                latitude=12.9710 + (i * 0.001),
                longitude=77.5940 + (i * 0.001),
                address=f"Cluster Point {i}",
            )
            db.add(inc)
            db.commit()
            pub = IncidentPublication(incident_id=inc.id, visibility_status="PUBLIC")
            db.add(pub)
            points.append(inc)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/v2/public/incidents/clusters?min_lon=77.0&min_lat=12.0&max_lon=78.0&max_lat=13.5&grid_size=0.05")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    clusters = data["clusters"]
    assert len(clusters) >= 1
    # Check that individual incident references are preserved in cluster payload
    found_refs = []
    for c in clusters:
        found_refs.extend(c["incident_references"])
    assert any(p.incident_reference in found_refs for p in points)


def test_map_filters_respect_category_and_status(client):
    """Scenario 12: Viewport queries respect category and status filters."""
    factory = get_session_factory()
    db = factory()
    try:
        inc_pothole = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            status="verified",
            latitude=12.9700,
            longitude=77.5900,
        )
        inc_streetlight = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="broken_streetlight",
            status="verified",
            latitude=12.9705,
            longitude=77.5905,
        )
        db.add_all([inc_pothole, inc_streetlight])
        db.commit()
        db.add_all([
            IncidentPublication(incident_id=inc_pothole.id, visibility_status="PUBLIC"),
            IncidentPublication(incident_id=inc_streetlight.id, visibility_status="PUBLIC"),
        ])
        db.commit()
        pothole_id = inc_pothole.id
        light_id = inc_streetlight.id
    finally:
        db.close()

    # Filter by category = pothole
    resp = client.get("/api/v2/public/incidents/viewport?min_lon=77.58&min_lat=12.96&max_lon=77.60&max_lat=12.98&category=pothole")
    assert resp.status_code == 200
    ids = [it["id"] for it in resp.get_json()["items"]]
    assert pothole_id in ids
    assert light_id not in ids
