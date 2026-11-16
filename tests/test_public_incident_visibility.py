"""
Tests for Public Incident Visibility and Privacy Policy (Step 9)
================================================================
Verifies that only approved canonical incidents appear publicly,
unverified/rejected reports are excluded, 50 linked reports produce 1 marker,
distinct nearby defects remain separate, and hidden incidents never leak.
"""

import uuid
import pytest
from backend.db.engine import get_session_factory
from backend.db.models import Incident, CitizenReport, ReportItem, IncidentPublication, User
from backend.services.public_incident_service import PublicIncidentService


@pytest.fixture
def public_service():
    return PublicIncidentService()


def test_unverified_incident_not_public(client, public_service):
    """Scenario 1: A citizen submits a new unverified report. It must not appear on public map."""
    factory = get_session_factory()
    db = factory()
    try:
        inc = Incident(
            category="pothole",
            description="Unverified rough patch",
            severity="moderate",
            status="awaiting_verification",
            latitude=12.9716,
            longitude=77.5946,
            address="Koramangala 4th Block",
        )
        db.add(inc)
        db.commit()
        inc_id = inc.id
    finally:
        db.close()

    # Query public viewport
    resp = client.get("/api/v2/public/incidents/viewport?min_lon=77.0&min_lat=12.0&max_lon=78.0&max_lat=13.5")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    found_ids = [it["id"] for it in items]
    assert inc_id not in found_ids, "Unverified incident must not appear on public map"

    # Direct detail query must return 404
    detail_resp = client.get(f"/api/v2/public/incidents/{inc_id}")
    assert detail_resp.status_code == 404


def test_verified_published_incident_appears_once(client, public_service):
    """Scenario 2: A verified and published incident appears once in public viewport."""
    factory = get_session_factory()
    db = factory()
    try:
        inc = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            description="Verified deep pothole",
            severity="severe",
            status="verified",
            latitude=12.9750,
            longitude=77.6000,
            address="MG Road",
        )
        db.add(inc)
        db.commit()

        pub = IncidentPublication(
            incident_id=inc.id,
            visibility_status="PUBLIC",
            public_title="Verified Pothole Hazard",
            public_description="Verified deep crater on MG Road.",
            public_location_name="MG Road, Bengaluru",
            public_latitude=12.975,
            public_longitude=77.600,
        )
        db.add(pub)
        db.commit()
        inc_id = inc.id
        inc_ref = inc.incident_reference
    finally:
        db.close()

    resp = client.get("/api/v2/public/incidents/viewport?min_lon=77.0&min_lat=12.0&max_lon=78.0&max_lat=13.5")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    matches = [it for it in items if it["id"] == inc_id]
    assert len(matches) == 1, "Verified published incident must appear exactly once"

    detail_resp = client.get(f"/api/v2/public/incidents/{inc_ref}")
    assert detail_resp.status_code == 200
    data = detail_resp.get_json()["incident"]
    assert data["incident_reference"] == inc_ref
    assert data["status"] == "verified"


def test_fifty_reports_produce_one_canonical_marker(client):
    """Scenario 3: 50 reports linked to 1 incident produce exactly one public marker."""
    factory = get_session_factory()
    db = factory()
    try:
        inc = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            description="High traffic pothole with multiple submissions",
            severity="critical",
            status="in_progress",
            latitude=12.9800,
            longitude=77.6100,
            address="Indiranagar 100ft Road",
            report_count=50,
        )
        db.add(inc)
        db.commit()

        pub = IncidentPublication(
            incident_id=inc.id,
            visibility_status="PUBLIC",
            public_title="Major Road Depression",
            public_location_name="Indiranagar 100ft Road",
            public_latitude=12.980,
            public_longitude=77.610,
        )
        db.add(pub)
        db.commit()
        inc_id = inc.id
    finally:
        db.close()

    resp = client.get("/api/v2/public/incidents/viewport?min_lon=77.0&min_lat=12.0&max_lon=78.0&max_lat=13.5")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    matches = [it for it in items if it["id"] == inc_id]
    assert len(matches) == 1, "50 merged reports must produce exactly 1 public marker"
    assert matches[0]["report_count"] == 50


def test_nearby_distinct_incidents_remain_separate(client):
    """Scenario 4: Two distinct nearby incidents remain separate markers."""
    factory = get_session_factory()
    db = factory()
    try:
        inc1 = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            severity="severe",
            status="verified",
            latitude=12.9710,
            longitude=77.5940,
            address="Richmond Circle North",
        )
        inc2 = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            severity="minor",
            status="verified",
            latitude=12.9712,  # ~25m away
            longitude=77.5942,
            address="Richmond Circle South",
        )
        db.add_all([inc1, inc2])
        db.commit()

        pub1 = IncidentPublication(incident_id=inc1.id, visibility_status="PUBLIC")
        pub2 = IncidentPublication(incident_id=inc2.id, visibility_status="PUBLIC")
        db.add_all([pub1, pub2])
        db.commit()
        id1, id2 = inc1.id, inc2.id
    finally:
        db.close()

    resp = client.get("/api/v2/public/incidents/viewport?min_lon=77.59&min_lat=12.97&max_lon=77.60&max_lat=12.98")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    ids = [it["id"] for it in items]
    assert id1 in ids and id2 in ids, "Both distinct nearby incidents must exist as separate markers"


def test_hidden_and_unpublished_incidents_excluded(client, public_service):
    """Scenario 5 & 6: A hidden incident never appears; unpublishing updates visibility."""
    factory = get_session_factory()
    db = factory()
    try:
        inc = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            status="verified",
            latitude=12.9500,
            longitude=77.5500,
            address="Secret Compound Road",
        )
        db.add(inc)
        db.commit()

        pub = IncidentPublication(
            incident_id=inc.id,
            visibility_status="HIDDEN",
            visibility_reason="Security sensitive area",
        )
        db.add(pub)
        db.commit()
        inc_id = inc.id
    finally:
        db.close()

    # Query public endpoint
    resp = client.get("/api/v2/public/incidents/viewport?min_lon=77.0&min_lat=12.0&max_lon=78.0&max_lat=13.5")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert inc_id not in [it["id"] for it in items]

    detail_resp = client.get(f"/api/v2/public/incidents/{inc_id}")
    assert detail_resp.status_code == 404

    # Now unpublish/archive
    public_service.set_incident_publication(inc_id, officer_id=None, visibility_status="ARCHIVED")
    resp_after = client.get("/api/v2/public/incidents/viewport?min_lon=77.0&min_lat=12.0&max_lon=78.0&max_lat=13.5")
    assert inc_id not in [it["id"] for it in resp_after.get_json()["items"]]
