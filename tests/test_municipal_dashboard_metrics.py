"""
Municipal Dashboard Metrics and Triage Queue Test Suite
=======================================================
Verifies 100% database-backed metrics aggregation, SLA breach detection,
category and priority breakdowns, and triage queue querying with multi-criteria filters.
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta

from backend.db.engine import get_session_factory
from backend.db.models import Incident, Department, User, ReportItem
from backend.services.municipal_dashboard_service import MunicipalDashboardService
from backend.services.department_management_service import DepartmentManagementService


@pytest.fixture
def dashboard_service():
    return MunicipalDashboardService()


@pytest.fixture
def dept_service():
    return DepartmentManagementService()


def test_dashboard_metrics_accurate_aggregation(app, dashboard_service):
    """Verifies that all metric counts match real database records with zero hardcoding."""
    db = get_session_factory()()

    # Clear any previous test incidents and report items
    db.query(ReportItem).delete()
    db.query(Incident).delete()
    db.commit()

    # Create test incidents
    i1 = Incident(id=str(uuid.uuid4()), description="P1", category="pothole", status="new", priority="normal", latitude=12.97, longitude=77.59)
    i2 = Incident(id=str(uuid.uuid4()), description="P2", category="pothole", status="awaiting_verification", priority="high", latitude=12.97, longitude=77.59)
    i3 = Incident(id=str(uuid.uuid4()), description="P3", category="drainage", status="assigned", priority="normal", latitude=12.97, longitude=77.59)
    i4 = Incident(id=str(uuid.uuid4()), description="P4", category="drainage", status="in_progress", priority="critical", latitude=12.97, longitude=77.59)
    i5 = Incident(id=str(uuid.uuid4()), description="P5", category="road_damage", status="on_hold", priority="normal", latitude=12.97, longitude=77.59)
    i6 = Incident(id=str(uuid.uuid4()), description="P6", category="pothole", status="resolved", priority="normal", latitude=12.97, longitude=77.59)
    i7 = Incident(id=str(uuid.uuid4()), description="P7", category="pothole", status="closed", priority="normal", latitude=12.97, longitude=77.59)
    db.add_all([i1, i2, i3, i4, i5, i6, i7])
    db.commit()
    db.close()

    metrics = dashboard_service.get_dashboard_metrics()

    assert metrics["total_registered"] == 7
    assert metrics["awaiting_verification"] == 2  # new + awaiting_verification
    assert metrics["in_progress"] == 2           # assigned + in_progress
    assert metrics["on_hold"] == 1
    assert metrics["resolved"] == 2              # resolved + closed
    assert metrics["by_category"]["pothole"] == 4
    assert metrics["by_category"]["drainage"] == 2
    assert metrics["by_priority"]["critical"] == 1


def test_sla_breach_detection(app, dashboard_service):
    """Detects active incidents that have exceeded maximum SLA target hours."""
    db = get_session_factory()()
    db.query(Incident).delete()
    db.commit()

    now = datetime.now(timezone.utc)
    # High priority SLA is 48 hours. Created 50 hours ago -> breached!
    old_time = now - timedelta(hours=50)

    breached_inc = Incident(
        id=str(uuid.uuid4()),
        description="Dangerous cave-in on highway",
        category="road_damage",
        status="in_progress",
        priority="high",
        latitude=12.97,
        longitude=77.59,
        created_at=old_time
    )

    # Fresh incident created 2 hours ago -> not breached
    fresh_inc = Incident(
        id=str(uuid.uuid4()),
        description="Fresh pothole report",
        category="pothole",
        status="in_progress",
        priority="high",
        latitude=12.97,
        longitude=77.59,
        created_at=now - timedelta(hours=2)
    )

    # Old resolved incident -> resolved incidents are not active SLA breaches
    resolved_inc = Incident(
        id=str(uuid.uuid4()),
        description="Old resolved issue",
        category="pothole",
        status="resolved",
        priority="critical",
        latitude=12.97,
        longitude=77.59,
        created_at=now - timedelta(hours=72)
    )

    db.add_all([breached_inc, fresh_inc, resolved_inc])
    db.commit()
    db.close()

    metrics = dashboard_service.get_dashboard_metrics()
    assert metrics["overdue_sla_count"] == 1


def test_triage_queue_filtering_and_search(app, dashboard_service, dept_service):
    """Queries triage queue with department, priority, status and search filters."""
    code = f"TRIAGE_{uuid.uuid4().hex[:6].upper()}"
    dept = dept_service.create_department(name=f"Triage Wing {code}", code=code)

    db = get_session_factory()()
    db.query(Incident).delete()
    db.commit()

    target_inc = Incident(
        id=str(uuid.uuid4()),
        incident_reference=f"INC-{uuid.uuid4().hex[:5].upper()}",
        description="Unique Landmark Bellandur flyover pothole",
        category="pothole",
        status="assigned",
        priority="critical",
        department_id=dept["id"],
        latitude=12.97,
        longitude=77.59
    )

    other_inc = Incident(
        id=str(uuid.uuid4()),
        incident_reference=f"INC-{uuid.uuid4().hex[:5].upper()}",
        description="Standard sidewalk crack",
        category="road_damage",
        status="new",
        priority="low",
        latitude=12.97,
        longitude=77.59
    )

    db.add_all([target_inc, other_inc])
    db.commit()
    db.close()

    # Search by text
    res = dashboard_service.list_triage_incidents(search_query="Bellandur")
    assert res["total"] == 1
    assert res["incidents"][0]["id"] == target_inc.id

    # Filter by department
    res_dept = dashboard_service.list_triage_incidents(department_id=dept["id"])
    assert res_dept["total"] == 1
    assert res_dept["incidents"][0]["department_code"] == code

    # Filter by priority
    res_prio = dashboard_service.list_triage_incidents(priority="critical")
    assert res_prio["total"] == 1
    assert res_prio["incidents"][0]["priority"] == "critical"
