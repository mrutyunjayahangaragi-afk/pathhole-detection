"""
Database Architecture, ORM Models, and Integrity Tests
======================================================

Verifies the normalized CivicLens schema:
- Table creation and index generation
- Multi-report to canonical incident relationships
- Multi-item reports and shared evidence assets
- Foreign key constraints (CASCADE, RESTRICT, SET NULL)
- Check constraints (severity, status, confidence)
- Transaction atomicity and rollback
- Legacy SQLite to normalized schema migration
"""

import os
import tempfile
import sqlite3
import pytest
from datetime import datetime, timezone
import uuid

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.db.engine import get_engine, reset_engine
from backend.db.init_schema import create_all_tables
from backend.db.session import transactional_session
from backend.db.models import (
    Base, User, Incident, CitizenReport, ReportItem,
    EvidenceAsset, ReportEvidence, DetectionRun, Detection,
    IncidentObservation, MatchDecision, IncidentStatusHistory,
    Department, IncidentAssignment, AuditLog,
)
from scripts.migrate_sqlite_to_pg import migrate


@pytest.fixture
def orm_db_path():
    """Isolated temporary SQLite database for ORM testing."""
    fd, path = tempfile.mkstemp(prefix="civiclens_orm_test_", suffix=".db")
    os.close(fd)
    yield path
    reset_engine()
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def orm_session(orm_db_path):
    """Provides a clean SQLAlchemy session bound to the temporary database."""
    url = f"sqlite:///{orm_db_path}"
    engine = get_engine(url)
    create_all_tables(url)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionFactory()
    yield session
    session.close()


# ─── 1. Schema & Table Existence ─────────────────────────────────────

def test_all_14_domain_tables_created(orm_db_path):
    url = f"sqlite:///{orm_db_path}"
    engine = get_engine(url)
    create_all_tables(url)

    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()

    expected_tables = {
        "users", "incidents_v2", "citizen_reports_v2", "report_items",
        "evidence_assets_v2", "report_evidence", "detection_runs", "detections_v3",
        "incident_observations_v2", "match_decisions_v2", "incident_status_history",
        "departments", "incident_assignments", "audit_logs_v2"
    }

    assert expected_tables.issubset(set(tables)), f"Missing tables: {expected_tables - set(tables)}"


# ─── 2. Multi-Report to One Canonical Incident ───────────────────────

def test_multiple_citizen_reports_link_to_one_canonical_incident(orm_session):
    # Create canonical incident
    inc = Incident(
        id=str(uuid.uuid4()),
        incident_reference="INC-001",
        category="pothole",
        severity="moderate",
        status="reported",
        latitude=12.9716,
        longitude=77.5946,
        report_count=3,
    )
    orm_session.add(inc)

    # 3 distinct citizens submit reports about this same incident
    for i in range(3):
        citizen = User(
            id=str(uuid.uuid4()),
            display_name=f"Citizen {i+1}",
            email=f"citizen{i+1}@example.com",
            role="citizen",
        )
        orm_session.add(citizen)

        report = CitizenReport(
            id=str(uuid.uuid4()),
            citizen_id=citizen.id,
            description=f"Pothole report from citizen {i+1}",
            status="linked",
        )
        orm_session.add(report)

        item = ReportItem(
            id=str(uuid.uuid4()),
            report_id=report.id,
            incident_id=inc.id,
            category="pothole",
            status="matched",
        )
        orm_session.add(item)

    orm_session.commit()

    # Verify canonical incident has 3 report items linked
    linked_items = orm_session.query(ReportItem).filter_by(incident_id=inc.id).all()
    assert len(linked_items) == 3
    assert all(item.incident_id == inc.id for item in linked_items)


# ─── 3. Multi-Item Single Report ─────────────────────────────────────

def test_single_citizen_report_can_contain_multiple_defect_items(orm_session):
    report = CitizenReport(
        id=str(uuid.uuid4()),
        description="Multiple defects on 5th cross road",
        status="submitted",
    )
    orm_session.add(report)

    # Item 1: Pothole
    item1 = ReportItem(
        id=str(uuid.uuid4()),
        report_id=report.id,
        category="pothole",
        description="Deep pothole near junction",
    )
    # Item 2: Broken streetlight
    item2 = ReportItem(
        id=str(uuid.uuid4()),
        report_id=report.id,
        category="broken_streetlight",
        description="Streetlight flickering and leaning",
    )
    orm_session.add_all([item1, item2])
    orm_session.commit()

    reloaded = orm_session.query(CitizenReport).filter_by(id=report.id).one()
    assert len(reloaded.items) == 2
    categories = {it.category for it in reloaded.items}
    assert categories == {"pothole", "broken_streetlight"}


# ─── 4. Shared Evidence & Deduplication ──────────────────────────────

def test_shared_evidence_asset_deduplication(orm_session):
    sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    asset = EvidenceAsset(
        id=str(uuid.uuid4()),
        content_sha256=sha,
        storage_key="uploads/photo1.jpg",
        media_type="image/jpeg",
    )
    orm_session.add(asset)

    report_a = CitizenReport(id=str(uuid.uuid4()), description="Report A")
    report_b = CitizenReport(id=str(uuid.uuid4()), description="Report B")
    orm_session.add_all([report_a, report_b])

    # Both reports reference the exact same underlying media file
    link_a = ReportEvidence(
        id=str(uuid.uuid4()),
        report_id=report_a.id,
        evidence_asset_id=asset.id,
        submitted_latitude=12.9716,
        submitted_longitude=77.5946,
    )
    link_b = ReportEvidence(
        id=str(uuid.uuid4()),
        report_id=report_b.id,
        evidence_asset_id=asset.id,
        submitted_latitude=12.9718,
        submitted_longitude=77.5947,
    )
    orm_session.add_all([link_a, link_b])
    orm_session.commit()

    # Duplicate upload with same sha256 must fail unique constraint
    duplicate_asset = EvidenceAsset(
        id=str(uuid.uuid4()),
        content_sha256=sha,
        storage_key="uploads/photo2.jpg",
    )
    orm_session.add(duplicate_asset)
    with pytest.raises(IntegrityError):
        orm_session.commit()
    orm_session.rollback()


# ─── 5. Detection Run & Multiple Detections ──────────────────────────

def test_detection_run_produces_multiple_detections(orm_session):
    asset = EvidenceAsset(
        id=str(uuid.uuid4()),
        content_sha256="abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
        storage_key="uploads/road_stereo.jpg",
    )
    orm_session.add(asset)

    run = DetectionRun(
        id=str(uuid.uuid4()),
        evidence_asset_id=asset.id,
        model_name="yolov8",
        model_version="v1.2",
        processing_status="completed",
    )
    orm_session.add(run)

    det1 = Detection(
        id=str(uuid.uuid4()),
        detection_run_id=run.id,
        detected_category="pothole",
        confidence_score=0.92,
        bbox_x=10, bbox_y=20, bbox_w=100, bbox_h=80,
        severity="moderate",
    )
    det2 = Detection(
        id=str(uuid.uuid4()),
        detection_run_id=run.id,
        detected_category="pothole",
        confidence_score=0.78,
        bbox_x=220, bbox_y=150, bbox_w=60, bbox_h=40,
        severity="minor",
    )
    orm_session.add_all([det1, det2])
    orm_session.commit()

    reloaded_run = orm_session.query(DetectionRun).filter_by(id=run.id).one()
    assert len(reloaded_run.detections) == 2


# ─── 6. Foreign Key Cascades & Restrictions ──────────────────────────

def test_fk_cascade_and_restrict_integrity(orm_session):
    # 1. CASCADE: Deleting report deletes report_items
    report = CitizenReport(id=str(uuid.uuid4()), description="Test report")
    orm_session.add(report)
    item = ReportItem(id=str(uuid.uuid4()), report_id=report.id, category="pothole")
    orm_session.add(item)
    orm_session.commit()

    orm_session.delete(report)
    orm_session.commit()

    assert orm_session.query(ReportItem).filter_by(id=item.id).first() is None

    # 2. RESTRICT: Cannot delete EvidenceAsset while ReportEvidence references it
    asset = EvidenceAsset(id=str(uuid.uuid4()), content_sha256="restrict_test_hash")
    orm_session.add(asset)
    rep2 = CitizenReport(id=str(uuid.uuid4()), description="Rep 2")
    orm_session.add(rep2)
    link = ReportEvidence(id=str(uuid.uuid4()), report_id=rep2.id, evidence_asset_id=asset.id)
    orm_session.add(link)
    orm_session.commit()

    orm_session.delete(asset)
    with pytest.raises(IntegrityError):
        orm_session.commit()
    orm_session.rollback()

    # 3. SET NULL: Deleting incident keeps report_item but sets incident_id to None
    inc = Incident(
        id=str(uuid.uuid4()),
        latitude=12.0, longitude=77.0,
        severity="minor", status="reported"
    )
    orm_session.add(inc)
    rep3 = CitizenReport(id=str(uuid.uuid4()), description="Rep 3")
    orm_session.add(rep3)
    item3 = ReportItem(id=str(uuid.uuid4()), report_id=rep3.id, incident_id=inc.id)
    orm_session.add(item3)
    orm_session.commit()

    orm_session.delete(inc)
    orm_session.commit()

    item_after = orm_session.query(ReportItem).filter_by(id=item3.id).one()
    assert item_after.incident_id is None


# ─── 7. Check Constraints ────────────────────────────────────────────

def test_check_constraints_enforced(orm_session):
    # Invalid severity
    inc_bad_sev = Incident(
        id=str(uuid.uuid4()),
        latitude=12.0, longitude=77.0,
        severity="catastrophic",  # invalid
        status="reported"
    )
    orm_session.add(inc_bad_sev)
    with pytest.raises(IntegrityError):
        orm_session.commit()
    orm_session.rollback()

    # Invalid status
    inc_bad_stat = Incident(
        id=str(uuid.uuid4()),
        latitude=12.0, longitude=77.0,
        severity="minor",
        status="unknown_status"  # invalid
    )
    orm_session.add(inc_bad_stat)
    with pytest.raises(IntegrityError):
        orm_session.commit()
    orm_session.rollback()

    # Invalid confidence score (> 1.0)
    asset = EvidenceAsset(id=str(uuid.uuid4()), content_sha256="test_conf_hash")
    orm_session.add(asset)
    run = DetectionRun(id=str(uuid.uuid4()), evidence_asset_id=asset.id)
    orm_session.add(run)
    det_bad = Detection(
        id=str(uuid.uuid4()),
        detection_run_id=run.id,
        confidence_score=1.5,  # invalid: > 1.0
    )
    orm_session.add(det_bad)
    with pytest.raises(IntegrityError):
        orm_session.commit()
    orm_session.rollback()


# ─── 8. Status History & Department Workflow ─────────────────────────

def test_status_history_and_department_assignment(orm_session):
    dept = Department(
        id=str(uuid.uuid4()),
        name="Roads & Infrastructure",
        contact_email="roads@bbmp.gov.in"
    )
    orm_session.add(dept)

    officer = User(
        id=str(uuid.uuid4()),
        display_name="Engineer Rao",
        role="municipal_officer",
        email="rao@bbmp.gov.in"
    )
    orm_session.add(officer)

    inc = Incident(
        id=str(uuid.uuid4()),
        latitude=12.95, longitude=77.58,
        severity="severe", status="reported"
    )
    orm_session.add(inc)
    orm_session.commit()

    # Status transition: reported -> scheduled
    hist = IncidentStatusHistory(
        id=str(uuid.uuid4()),
        incident_id=inc.id,
        previous_status="reported",
        new_status="scheduled",
        changed_by=officer.id,
        reason="Scheduled for repair in Ward 112",
    )
    inc.status = "scheduled"
    orm_session.add(hist)

    # Department assignment
    assign = IncidentAssignment(
        id=str(uuid.uuid4()),
        incident_id=inc.id,
        department_id=dept.id,
        assigned_to=officer.id,
        priority="high",
        status="assigned",
    )
    orm_session.add(assign)
    orm_session.commit()

    reloaded_inc = orm_session.query(Incident).filter_by(id=inc.id).one()
    assert reloaded_inc.status == "scheduled"
    assert reloaded_inc.status_history.count() == 1
    assert reloaded_inc.assignments.count() == 1
    assert reloaded_inc.assignments.first().department.name == "Roads & Infrastructure"


# ─── 9. Transaction Rollback Atomicity ────────────────────────────────

def test_transaction_rollback_prevents_partial_writes(orm_db_path):
    url = f"sqlite:///{orm_db_path}"
    create_all_tables(url)

    try:
        with transactional_session(url) as s:
            u = User(id=str(uuid.uuid4()), display_name="Atomicity Test", role="citizen")
            s.add(u)
            # Deliberately raise error inside context manager
            raise RuntimeError("Simulated mid-operation transaction failure")
    except RuntimeError:
        pass

    # Verify user was NOT persisted
    SessionFactory = sessionmaker(bind=get_engine(url))
    s2 = SessionFactory()
    assert s2.query(User).filter_by(display_name="Atomicity Test").first() is None
    s2.close()


# ─── 10. Migration Script Verification ───────────────────────────────

def test_migration_from_sqlite_legacy_detections(orm_db_path):
    """Creates mock legacy detections in a SQLite db and runs migrate()."""
    conn = sqlite3.connect(orm_db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE detections (
            id TEXT PRIMARY KEY,
            vehicle_id TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            severity TEXT NOT NULL,
            est_depth_cm REAL,
            confidence REAL,
            image_ref TEXT,
            timestamp REAL NOT NULL,
            status TEXT NOT NULL,
            report_count INTEGER NOT NULL,
            address TEXT
        )
    """)
    for i in range(5):
        cur.execute("""
            INSERT INTO detections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"leg-uuid-{i}", f"car-{i}", 12.9 + (i * 0.001), 77.5 + (i * 0.001),
            "severe" if i % 2 == 0 else "minor", 5.5, 0.85, f"img_{i}.jpg",
            1785000000.0 + i, "reported", 1 + i, f"Address {i}"
        ))
    conn.commit()
    conn.close()

    # Run migration
    url = f"sqlite:///{orm_db_path}"
    ok = migrate(source_db_path=orm_db_path, target_url=url, dry_run=False)
    assert ok is True

    # Verify counts in normalized schema
    SessionFactory = sessionmaker(bind=get_engine(url))
    s = SessionFactory()
    incidents = s.query(Incident).all()
    assert len(incidents) == 5
    assert all(inc.id.startswith("leg-uuid-") for inc in incidents)
    observations = s.query(IncidentObservation).all()
    assert len(observations) == 5
    s.close()
