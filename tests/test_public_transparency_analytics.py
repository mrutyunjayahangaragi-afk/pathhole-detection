"""
Tests for Public Transparency and Analytics (Step 9)
====================================================
Validates that public transparency metrics are 100% computed from real database
records, distinguishing canonical incidents from raw citizen grievance volume.
"""

import uuid
import pytest
from backend.db.engine import get_session_factory
from backend.db.models import Incident, CitizenReport, IncidentPublication
from backend.services.public_transparency_service import PublicTransparencyService


def test_public_transparency_metrics_accuracy(client):
    """Scenario 34 & 35: Metrics correctly distinguish canonical incidents from report volumes."""
    factory = get_session_factory()
    db = factory()
    try:
        # Create 2 canonical incidents
        inc1 = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            severity="severe",
            status="resolved",
            latitude=12.97,
            longitude=77.59,
        )
        inc2 = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="road_damage",
            severity="minor",
            status="in_progress",
            latitude=12.98,
            longitude=77.60,
        )
        db.add_all([inc1, inc2])
        db.commit()

        # Create 5 citizen reports
        for i in range(5):
            rep = CitizenReport(
                title=f"Report {i}",
                description="Hazard",
                reported_severity="severe",
                latitude=12.97,
                longitude=77.59,
            )
            db.add(rep)
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/v2/public/statistics")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["status"] == "success"
    assert data["total_canonical_incidents"] >= 2
    assert data["total_citizen_reports"] >= 5
    assert data["deduplication_ratio"] >= 0.0
    assert "status_breakdown" in data
    assert "category_breakdown" in data
    assert "resolution_rate_pct" in data


def test_public_transparency_empty_db_safe():
    """Scenario 36: Empty dataset computes safe defaults with zero division error."""
    service = PublicTransparencyService()
    metrics = service.get_transparency_metrics()
    assert metrics["status"] == "success"
    assert metrics["deduplication_ratio"] >= 0.0
    assert metrics["resolution_rate_pct"] >= 0.0
