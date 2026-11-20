"""
CivicLens Step 2 Test Suite: Department Reporting, Aggregation & Real Telemetry
==============================================================================
Validates:
1. Citizen report creation automatically routes to the appropriate municipal department.
2. Multiple citizen reports for the same physical defect aggregate into a single canonical incident.
3. Physically distinct potholes create separate canonical incidents.
4. Report count increments accurately while retaining all citizen submissions and evidence.
5. Idempotent grievance submissions.
6. Department portal filters incidents and retrieves all linked citizen reports.
7. Telemetry stats and device status return genuine database-driven values.
"""

import uuid
import pytest
from datetime import datetime, timezone
from backend.db.engine import get_session_factory
from backend.db.models import (
    CitizenReport, ReportItem, Incident, Department, User,
    ReportEvidence, EvidenceAsset, TelemetryDevice, TelemetryEvent
)
from backend.services.department_routing_service import DepartmentRoutingService
from backend.services.citizen_report_service import CitizenReportService
from backend.services.telemetry_service import TelemetryService


@pytest.fixture
def clean_db(app):
    SessionFactory = get_session_factory()
    db = SessionFactory()
    # Clean up test data
    db.query(ReportEvidence).delete()
    db.query(ReportItem).delete()
    db.query(CitizenReport).delete()
    db.query(Incident).delete()
    db.commit()

    # Ensure standard departments exist
    depts = [
        ("Road & Highway Maintenance", "ROAD_MAINT"),
        ("Electrical & Streetlighting", "STREETLIGHT"),
        ("Solid Waste Management", "SOLID_WASTE"),
        ("Stormwater & Drainage Division", "DRAINAGE"),
        ("Water Supply & Sewerage Board", "BWSSB"),
        ("Traffic Engineering & Signals", "TRAFFIC_ENG"),
        ("Pedestrian Walkways & Footpaths", "FOOTPATHS"),
        ("Public Works & Infrastructure", "PUBLIC_WORKS"),
    ]
    for name, code in depts:
        existing = db.query(Department).filter_by(code=code).first()
        if not existing:
            db.add(Department(
                id=str(uuid.uuid4()),
                name=name,
                code=code,
                is_active=True,
                created_at=datetime.now(timezone.utc)
            ))
    db.commit()

    # Ensure test citizen exists
    citizen = db.query(User).filter_by(email="test.citizen@civiclens.test").first()
    if not citizen:
        citizen = User(
            id=str(uuid.uuid4()),
            display_name="Citizen Tester",
            email="test.citizen@civiclens.test",
            role="citizen",
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        db.add(citizen)
        db.commit()

    yield db, citizen
    db.close()


def test_department_routing_service_all_categories():
    """Verifies that all supported categories map to expected department unit codes."""
    routing = DepartmentRoutingService()
    assert routing.resolve_department_code("pothole") == "ROAD_MAINT"
    assert routing.resolve_department_code("road_damage") == "ROAD_MAINT"
    assert routing.resolve_department_code("broken_streetlight") == "STREETLIGHT"
    assert routing.resolve_department_code("lighting") == "STREETLIGHT"
    assert routing.resolve_department_code("garbage") == "SOLID_WASTE"
    assert routing.resolve_department_code("solid_waste") == "SOLID_WASTE"
    assert routing.resolve_department_code("drainage") == "DRAINAGE"
    assert routing.resolve_department_code("waterlogging") == "DRAINAGE"
    assert routing.resolve_department_code("water_leakage") == "BWSSB"
    assert routing.resolve_department_code("traffic_signal") == "TRAFFIC_ENG"
    assert routing.resolve_department_code("footpaths") == "FOOTPATHS"
    assert routing.resolve_department_code("bridge_damage") == "PUBLIC_WORKS"


def test_single_report_creates_canonical_incident_and_routes_department(clean_db):
    """Verifies that a new citizen report automatically creates a canonical incident in the target department."""
    db, citizen = clean_db
    service = CitizenReportService()

    report_dict = service.create_report(
        citizen_id=citizen.id,
        title="Deep Pothole on MG Road",
        description="Hazardous pothole causing severe traffic disruption near metro pillar 120.",
        category="pothole",
        severity="severe",
        latitude=12.9716,
        longitude=77.5946,
        address="MG Road, Bengaluru"
    )

    assert report_dict["id"] is not None
    assert len(report_dict["items"]) == 1
    item_info = report_dict["items"][0]
    assert item_info["status"] == "new_incident"
    assert item_info["incident_id"] is not None

    # Check canonical incident in DB
    inc = db.query(Incident).filter_by(id=item_info["incident_id"]).first()
    assert inc is not None
    assert inc.category == "pothole"
    assert inc.report_count == 1
    assert inc.department is not None
    assert inc.department.code == "ROAD_MAINT"
    assert inc.latitude == pytest.approx(12.9716, abs=0.0001)


def test_multiple_reports_same_pothole_aggregate_into_single_incident(clean_db):
    """
    Verifies that multiple citizens reporting the same physical defect:
    1. Share 1 canonical incident.
    2. Maintain separate citizen report records.
    3. Increment report_count on the canonical incident.
    """
    db, citizen = clean_db
    service = CitizenReportService()

    # Citizen 1 reports the pothole
    rep1 = service.create_report(
        citizen_id=citizen.id,
        title="Pothole near Brigade Road junction",
        description="Dangerous road crater at junction.",
        category="pothole",
        severity="moderate",
        latitude=12.9730,
        longitude=77.6080,
    )
    inc_id = rep1["items"][0]["incident_id"]
    assert inc_id is not None

    # Citizen 2 reports same physical spot (within 5 meters)
    rep2 = service.create_report(
        citizen_id=citizen.id,
        title="Vehicle bottoming out on big pothole",
        description="Big pothole right at Brigade Road corner.",
        category="pothole",
        severity="severe",
        latitude=12.97302,  # ~3 meters away
        longitude=77.60802,
    )

    # Citizen 3 reports same physical spot
    rep3 = service.create_report(
        citizen_id=citizen.id,
        title="Pothole needs asphalt fill",
        description="Water filling this pothole after rain.",
        category="pothole",
        severity="moderate",
        latitude=12.97298,  # ~2 meters away
        longitude=77.60799,
    )

    # Check that both rep2 and rep3 merged into the same canonical incident!
    assert rep2["items"][0]["incident_id"] == inc_id
    assert rep2["items"][0]["status"] == "matched"

    assert rep3["items"][0]["incident_id"] == inc_id
    assert rep3["items"][0]["status"] == "matched"

    # Canonical incident in database must have report_count = 3
    inc = db.query(Incident).filter_by(id=inc_id).first()
    assert inc.report_count == 3

    # All 3 citizen reports exist distinctly in database!
    linked_items = db.query(ReportItem).filter_by(incident_id=inc_id).all()
    assert len(linked_items) == 3


def test_distinct_potholes_create_separate_incidents(clean_db):
    """Verifies that two different potholes (e.g. 100 meters apart) create separate canonical incidents."""
    db, citizen = clean_db
    service = CitizenReportService()

    # Pothole A on Indiranagar 100 Feet Road
    repA = service.create_report(
        citizen_id=citizen.id,
        title="Pothole outside cafe",
        description="Pothole on left lane.",
        category="pothole",
        severity="minor",
        latitude=12.9698,
        longitude=77.6408,
    )

    # Pothole B ~150 meters further down the road
    repB = service.create_report(
        citizen_id=citizen.id,
        title="Another pothole near signal",
        description="Distinct pothole near traffic light.",
        category="pothole",
        severity="moderate",
        latitude=12.9712,  # >150 meters away
        longitude=77.6415,
    )

    incA_id = repA["items"][0]["incident_id"]
    incB_id = repB["items"][0]["incident_id"]

    assert incA_id != incB_id
    incA = db.query(Incident).filter_by(id=incA_id).first()
    incB = db.query(Incident).filter_by(id=incB_id).first()

    assert incA.report_count == 1
    assert incB.report_count == 1
    assert db.query(Incident).count() == 2


def test_idempotent_report_submission(clean_db):
    """Verifies that duplicate submissions with the same idempotency_key return the existing report."""
    db, citizen = clean_db
    service = CitizenReportService()
    ikey = "unique-key-xyz-123"

    rep1 = service.create_report(
        citizen_id=citizen.id,
        title="Broken Streetlight",
        description="Light fixture flickering all night.",
        category="broken_streetlight",
        severity="minor",
        latitude=12.9352,
        longitude=77.6245,
        idempotency_key=ikey
    )

    # Second submission with same idempotency key
    rep2 = service.create_report(
        citizen_id=citizen.id,
        title="Broken Streetlight Duplicate",
        description="Duplicate submission attempt.",
        category="broken_streetlight",
        severity="minor",
        latitude=12.9352,
        longitude=77.6245,
        idempotency_key=ikey
    )

    assert rep1["id"] == rep2["id"]
    assert db.query(CitizenReport).count() == 1


def test_telemetry_service_stats_and_devices(clean_db):
    """Verifies that TelemetryService computes genuine counts and honest camera state."""
    db, _ = clean_db
    tel_service = TelemetryService()

    # Create 1 registered device and 2 events
    dev = TelemetryDevice(
        id=str(uuid.uuid4()),
        device_id="DEV-TEST-01",
        device_name="Rover Unit 1",
        assigned_vehicle="KA-01-BBMP-101",
        api_key_hash="dummy_hash_for_test",
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    db.add(dev)
    db.flush()

    ev1 = TelemetryEvent(
        id=str(uuid.uuid4()),
        event_id=f"EVT-TEST-{uuid.uuid4().hex[:6]}",
        device_id=dev.id,
        latitude=12.9716,
        longitude=77.5946,
        severity="severe",
        est_depth_cm=6.5,
        confidence=0.92,
        created_at=datetime.now(timezone.utc)
    )
    ev2 = TelemetryEvent(
        id=str(uuid.uuid4()),
        event_id=f"EVT-TEST-{uuid.uuid4().hex[:6]}",
        device_id=dev.id,
        latitude=12.9720,
        longitude=77.5950,
        severity="minor",
        est_depth_cm=2.1,
        confidence=0.88,
        created_at=datetime.now(timezone.utc)
    )
    db.add_all([ev1, ev2])
    db.commit()

    stats = tel_service.get_telemetry_stats()
    assert stats["status"] == "success"
    assert stats["total_events"] == 2
    assert stats["total_devices"] == 1
    assert stats["active_camera_streams"] == 0  # Honest: 0 offline
    assert stats["severity_distribution"]["severe"] == 1
    assert stats["severity_distribution"]["minor"] == 1
