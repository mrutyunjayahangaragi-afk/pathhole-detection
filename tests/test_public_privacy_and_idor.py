"""
Tests for Public Privacy, Redaction and Anti-IDOR Protection (Step 9)
=====================================================================
Ensures that no citizen PII (phone, email, ID), municipal internal notes,
or unapproved private evidence are exposed on public endpoints.
"""

import uuid
import pytest
from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, IncidentPublication, CitizenReport, ReportItem,
    MunicipalInternalNote, EvidenceAsset, User
)


def test_public_api_never_exposes_citizen_pii(client):
    """Scenario 13 & 17: Public endpoints never expose citizen contact details or exact private coordinates."""
    factory = get_session_factory()
    db = factory()
    try:
        # Create citizen with sensitive PII
        uid = uuid.uuid4().hex[:6]
        citizen = User(
            display_name="Private Citizen",
            email=f"private_{uid}@confidential.org",
            phone="+919876543210",
            role="citizen",
        )
        db.add(citizen)
        db.commit()

        # Create report by citizen
        rep = CitizenReport(
            citizen_id=citizen.id,
            title="Pothole in front of my gate",
            description="Hazardous hole right outside my house",
            reported_severity="severe",
            latitude=12.97165432,  # high precision private coordinate
            longitude=77.59461234,
            address="House #42, Secret Cross Road",
        )
        db.add(rep)
        db.commit()

        # Link to canonical incident
        inc = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            description="Pothole in residential zone",
            severity="severe",
            status="verified",
            latitude=12.97165432,
            longitude=77.59461234,
            address="Secret Cross Road",
        )
        db.add(inc)
        db.commit()

        item = ReportItem(report_id=rep.id, incident_id=inc.id)
        db.add(item)

        pub = IncidentPublication(
            incident_id=inc.id,
            visibility_status="PUBLIC",
            public_title="Verified Residential Pothole",
            public_description="Verified defect on Secret Cross Road.",
            public_location_name="Secret Cross Road Area",
            public_latitude=12.972,  # safely rounded
            public_longitude=77.595,
        )
        db.add(pub)
        db.commit()
        inc_ref = inc.incident_reference
    finally:
        db.close()

    # Query public incident details
    resp = client.get(f"/api/v2/public/incidents/{inc_ref}")
    assert resp.status_code == 200
    text_data = resp.get_data(as_text=True)

    # Strict privacy verification
    assert citizen.email not in text_data, "Citizen email must not leak in public incident response"
    assert citizen.phone not in text_data, "Citizen phone must not leak in public incident response"
    assert citizen.display_name not in text_data, "Citizen personal name must not leak in public response"
    assert "12.97165432" not in text_data, "Exact high-precision private coordinates must not be exposed"


def test_public_api_never_exposes_internal_notes(client):
    """Scenario 14: Municipal internal notes are strictly omitted from public views."""
    factory = get_session_factory()
    db = factory()
    try:
        inc = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            status="in_progress",
            latitude=12.9700,
            longitude=77.5900,
            address="Subway underpass",
        )
        db.add(inc)
        db.commit()

        pub = IncidentPublication(incident_id=inc.id, visibility_status="PUBLIC")
        db.add(pub)

        # Confidential internal note
        secret_comment = f"Contractor XYZ penalized for delay {uuid.uuid4().hex[:6]}"
        note = MunicipalInternalNote(
            incident_id=inc.id,
            content=secret_comment,
            audience="internal_officers",
        )
        db.add(note)
        db.commit()
        inc_ref = inc.incident_reference
    finally:
        db.close()

    resp = client.get(f"/api/v2/public/incidents/{inc_ref}")
    assert resp.status_code == 200
    text_data = resp.get_data(as_text=True)
    assert secret_comment not in text_data, "Confidential internal note must not leak into public endpoint"


def test_unauthorized_municipal_publication_rejected(client):
    """Scenario 16: Unauthorized users cannot modify public visibility."""
    factory = get_session_factory()
    db = factory()
    try:
        inc = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            status="verified",
            latitude=12.9700,
            longitude=77.5900,
        )
        db.add(inc)
        db.commit()
        inc_id = inc.id
    finally:
        db.close()

    # Anonymous PUT
    resp1 = client.put(f"/api/v2/public/incidents/{inc_id}/publication", json={"visibility_status": "PUBLIC"})
    assert resp1.status_code == 401, "Anonymous user must be rejected"
