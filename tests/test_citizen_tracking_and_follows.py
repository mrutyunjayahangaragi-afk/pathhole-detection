"""
Tests for Citizen Tracking and Incident Follows (Step 9)
========================================================
Validates independent citizen report tracking, anti-IDOR protection,
incident follow and unfollow workflows, and idempotent duplicate handling.
"""

import uuid
import pytest
from backend.db.engine import get_session_factory
from backend.db.models import Incident, CitizenReport, ReportItem, IncidentPublication, User
from backend.services.auth_service import AuthService
from backend.services.incident_follow_service import IncidentFollowService


def _register_user(client, role="citizen") -> tuple[str, str]:
    uid = uuid.uuid4().hex[:6]
    pwd = "Password123!"
    auth = AuthService()
    user_dict = auth.register_citizen(
        display_name=f"User {uid}",
        email=f"user_{uid}@example.com",
        password=pwd,
        confirm_password=pwd,
    )
    if role != "citizen":
        factory = get_session_factory()
        db = factory()
        u = db.query(User).filter_by(id=user_dict["id"]).first()
        u.role = role
        db.commit()
        db.close()

    res = client.post("/api/v1/auth/login", json={"email": f"user_{uid}@example.com", "password": pwd})
    token = res.get_json()["token"]
    return user_dict["id"], token


def test_citizen_can_track_own_report_only(client):
    """Scenario 18 & 19: Citizen sees only own reports; cannot access another citizen's report."""
    user1_id, token1 = _register_user(client)
    user2_id, token2 = _register_user(client)

    factory = get_session_factory()
    db = factory()
    try:
        rep1 = CitizenReport(
            citizen_id=user1_id,
            title="User 1 pothole report",
            description="Deep crater",
            reported_severity="severe",
            status="under_review",
            latitude=12.9716,
            longitude=77.5946,
        )
        db.add(rep1)
        db.commit()
        rep1_id = rep1.id
    finally:
        db.close()

    # User 1 tracking own report -> 200 OK
    resp1 = client.get(
        f"/api/v2/citizens/reports/{rep1_id}/tracking",
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert resp1.status_code == 200
    data1 = resp1.get_json()["report"]
    assert data1["id"] == rep1_id
    assert data1["report_status"] == "under_review"

    # User 2 attempting to track User 1's report -> 403 Forbidden
    resp2 = client.get(
        f"/api/v2/citizens/reports/{rep1_id}/tracking",
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert resp2.status_code == 403, "Anti-IDOR must reject accessing another citizen's report"


def test_citizen_follow_and_unfollow_incident(client):
    """Scenario 20 & 21: Citizen follows/unfollows incident, duplicate follows are idempotent."""
    user_id, token = _register_user(client)

    factory = get_session_factory()
    db = factory()
    try:
        inc = Incident(
            incident_reference=f"INC-{uuid.uuid4().hex[:6].upper()}",
            category="pothole",
            status="verified",
            latitude=12.9716,
            longitude=77.5946,
            address="Commercial Street",
        )
        db.add(inc)
        db.commit()
        pub = IncidentPublication(incident_id=inc.id, visibility_status="PUBLIC")
        db.add(pub)
        db.commit()
        inc_id = inc.id
    finally:
        db.close()

    # 1. Follow incident
    follow_resp = client.post(
        f"/api/v2/citizens/incidents/{inc_id}/follow",
        headers={"Authorization": f"Bearer {token}"},
        json={"channels": "in_app,email"}
    )
    assert follow_resp.status_code == 200
    assert follow_resp.get_json()["action"] == "followed"

    # 2. Duplicate follow request -> Idempotent
    dup_resp = client.post(
        f"/api/v2/citizens/incidents/{inc_id}/follow",
        headers={"Authorization": f"Bearer {token}"},
        json={"channels": "in_app,sms"}
    )
    assert dup_resp.status_code == 200
    assert dup_resp.get_json()["action"] == "already_following"

    # 3. Verify in followed list
    list_resp = client.get(
        "/api/v2/citizens/incidents/followed",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert list_resp.status_code == 200
    followed_items = list_resp.get_json()["items"]
    assert any(it["incident_id"] == inc_id for it in followed_items)

    # 4. Unfollow incident
    unfollow_resp = client.delete(
        f"/api/v2/citizens/incidents/{inc_id}/follow",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert unfollow_resp.status_code == 200
    assert unfollow_resp.get_json()["action"] == "unfollowed"

    # Verify removed from list
    list_after = client.get(
        "/api/v2/citizens/incidents/followed",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert not any(it["incident_id"] == inc_id for it in list_after.get_json()["items"])
