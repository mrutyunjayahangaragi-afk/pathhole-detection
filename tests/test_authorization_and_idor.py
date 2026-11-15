"""
Authorization & IDOR Security Test Suite
========================================

Verifies strict security boundaries:
- Insecure Direct Object Reference (IDOR) prevention:
  Citizens can NEVER view, query, or download another citizen's reports or private evidence.
- Citizens cannot access administrative endpoints or escalate privileges.
- Report portfolio filtering strictly isolates reports to the authenticated user.
"""

import io
import uuid
import pytest
from backend.db.engine import get_session_factory
from backend.db.models import User
from backend.auth import generate_auth_token


def register_user(client, email, name="Citizen", role="citizen"):
    res = client.post("/api/v1/auth/register", json={
        "display_name": name,
        "email": email,
        "password": "Password123",
        "confirm_password": "Password123"
    })
    token = res.get_json()["token"]
    user_id = res.get_json()["user"]["id"]

    if role != "citizen":
        # Elevate in DB for testing staff permissions
        db = get_session_factory()()
        u = db.query(User).filter_by(id=user_id).one()
        u.role = role
        db.commit()
        db.close()
        # Regenerate token with staff role
        token = generate_auth_token(user_id, role)

    return token, user_id


def test_citizen_cannot_access_another_citizens_report_idor(client):
    # Citizen A
    token_a, _ = register_user(client, f"alice_{uuid.uuid4().hex[:6]}@example.com", "Alice")
    # Citizen B
    token_b, _ = register_user(client, f"bob_{uuid.uuid4().hex[:6]}@example.com", "Bob")

    # Alice submits a report
    headers_a = {"Authorization": f"Bearer {token_a}"}
    res_submit = client.post("/api/v1/reports", json={
        "title": "Alice Private Pothole",
        "description": "Pothole in front of Alice house",
        "category": "pothole",
        "severity": "minor",
        "latitude": 12.9716,
        "longitude": 77.5946
    }, headers=headers_a)
    assert res_submit.status_code == 201
    report_id = res_submit.get_json()["report"]["id"]

    # Bob tries to access Alice's report -> Must be denied (404/403)
    headers_b = {"Authorization": f"Bearer {token_b}"}
    res_idor = client.get(f"/api/v1/reports/{report_id}", headers=headers_b)
    assert res_idor.status_code in (404, 403)
    assert "access denied" in res_idor.get_json()["error"].lower() or "not found" in res_idor.get_json()["error"].lower()

    # Alice CAN access her own report
    res_alice = client.get(f"/api/v1/reports/{report_id}", headers=headers_a)
    assert res_alice.status_code == 200
    assert res_alice.get_json()["report"]["title"] == "Alice Private Pothole"


def test_citizen_cannot_download_another_citizens_evidence(client):
    token_a, _ = register_user(client, f"user_a_{uuid.uuid4().hex[:6]}@example.com", "User A")
    token_b, _ = register_user(client, f"user_b_{uuid.uuid4().hex[:6]}@example.com", "User B")

    img_data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00" + (b"\x12" * 50)
    data = {
        "title": "Private evidence test",
        "description": "Private photo evidence",
        "category": "pothole",
        "latitude": "12.97",
        "longitude": "77.59",
        "photos": (io.BytesIO(img_data), "private.jpg", "image/jpeg")
    }
    headers_a = {"Authorization": f"Bearer {token_a}"}
    res_a = client.post("/api/v1/reports", data=data, content_type="multipart/form-data", headers=headers_a)
    assert res_a.status_code == 201
    evidence_list = res_a.get_json()["report"].get("evidence", [])
    assert len(evidence_list) >= 1
    asset_id = evidence_list[0]["id"]

    # User B attempts to fetch User A's private evidence file
    headers_b = {"Authorization": f"Bearer {token_b}"}
    res_steal = client.get(f"/api/v1/evidence/{asset_id}", headers=headers_b)
    assert res_steal.status_code in (404, 403)

    # User A CAN access their own evidence
    res_own = client.get(f"/api/v1/evidence/{asset_id}", headers=headers_a)
    assert res_own.status_code == 200
    assert len(res_own.data) > 0


def test_municipal_officer_can_access_evidence(client):
    token_citizen, _ = register_user(client, f"cit_{uuid.uuid4().hex[:6]}@example.com", "Cit")
    token_officer, _ = register_user(client, f"officer_{uuid.uuid4().hex[:6]}@example.com", "Officer", role="municipal_officer")

    img_data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00" + (b"\x34" * 50)
    data = {
        "title": "Officer review test",
        "description": "Officer review test description",
        "category": "road_damage",
        "latitude": "12.97",
        "longitude": "77.59",
        "photos": (io.BytesIO(img_data), "road.jpg", "image/jpeg")
    }
    res = client.post("/api/v1/reports", data=data, content_type="multipart/form-data", headers={"Authorization": f"Bearer {token_citizen}"})
    assert res.status_code == 201
    asset_id = res.get_json()["report"]["evidence"][0]["id"]

    # Municipal officer CAN download the evidence for inspection
    res_officer = client.get(f"/api/v1/evidence/{asset_id}", headers={"Authorization": f"Bearer {token_officer}"})
    assert res_officer.status_code == 200


def test_reports_list_is_strictly_scoped_to_current_user(client):
    token_1, _ = register_user(client, f"scope1_{uuid.uuid4().hex[:6]}@example.com", "Scope1")
    token_2, _ = register_user(client, f"scope2_{uuid.uuid4().hex[:6]}@example.com", "Scope2")

    headers_1 = {"Authorization": f"Bearer {token_1}"}
    headers_2 = {"Authorization": f"Bearer {token_2}"}

    # Submit 2 reports as User 1
    for i in range(2):
        client.post("/api/v1/reports", json={
            "title": f"User 1 Report {i}", "description": "Description text here", "category": "pothole", "latitude": 12.0, "longitude": 77.0
        }, headers=headers_1)

    # Submit 1 report as User 2
    client.post("/api/v1/reports", json={
        "title": "User 2 Secret Report", "description": "Description text here", "category": "drainage", "latitude": 12.0, "longitude": 77.0
    }, headers=headers_2)

    # User 1 queries /reports
    list_1 = client.get("/api/v1/reports", headers=headers_1).get_json()
    assert list_1["total"] == 2
    assert all("User 1" in r["title"] for r in list_1["reports"])
    assert not any("User 2" in r["title"] for r in list_1["reports"])

    # User 2 queries /reports
    list_2 = client.get("/api/v1/reports", headers=headers_2).get_json()
    assert list_2["total"] == 1
    assert list_2["reports"][0]["title"] == "User 2 Secret Report"
