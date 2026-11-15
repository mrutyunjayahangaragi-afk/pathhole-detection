"""End-to-end integration test verifying the complete Citizen user journey:
1. Citizen Registration with Kannada preferred language
2. Profile retrieval and initial empty DB stats
3. Citizen Grievance Submission with Unicode text and location
4. Verification of DB counts update (total=1, submitted=1)
5. Citizen Report Listing (user scoped)
6. Fetching single report details
7. Profile update (contact info & language)
8. Frontend HTML route availability
"""

import json
import uuid
import pytest


def test_full_citizen_journey_end_to_end(client, clean_db):
    # 1. Verify frontend HTML endpoints return 200
    for path in [
        "/citizen-login.html",
        "/citizen-dashboard.html",
        "/citizen-report.html",
        "/my-reports.html",
        "/report-detail.html",
    ]:
        res = client.get(path)
        assert res.status_code == 200, f"Route {path} failed: {res.status_code}"
        assert b"CivicLens" in res.data

    # 2. Register Citizen
    email = f"kavitha_{uuid.uuid4().hex[:8]}@example.com"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "display_name": "Kavitha Rao",
            "email": email,
            "phone": "+91 9988776655",
            "preferred_language": "kn",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
        },
    )
    assert reg_res.status_code == 201
    reg_data = reg_res.get_json()
    token = reg_data["token"]
    user = reg_data["user"]
    assert user["display_name"] == "Kavitha Rao"
    assert user["role"] == "citizen"
    assert user["preferred_language"] == "kn"

    auth_header = {"Authorization": f"Bearer {token}"}

    # 3. Check /me stats initially 0
    me_res = client.get("/api/v1/auth/me", headers=auth_header)
    assert me_res.status_code == 200
    me_data = me_res.get_json()
    assert me_data["report_stats"]["total"] == 0

    # 4. Submit Grievance Report
    idem_key = str(uuid.uuid4())
    rep_res = client.post(
        "/api/v1/reports",
        json={
            "title": "ದೊಡ್ಡ ಗುಂಡಿ (Severe pothole on 100ft road)",
            "category": "pothole",
            "severity": "severe",
            "description": "ರಸ್ತೆಯಲ್ಲಿ ಆಳವಾದ ಗುಂಡಿ ಬಿದ್ದಿದೆ, ವಾಹನ ಸವಾರರಿಗೆ ತೊಂದರೆ. Deep hole near water tank.",
            "latitude": 12.9719,
            "longitude": 77.5948,
            "is_manual_location": False,
            "location_accuracy_m": 4.5,
            "address": "100ft Rd, Indiranagar, Bengaluru",
        },
        headers={**auth_header, "Idempotency-Key": idem_key},
    )
    assert rep_res.status_code == 201
    rep_data = rep_res.get_json()
    report = rep_data["report"]
    report_id = report["id"]
    ref_code = report["reference_code"]
    assert ref_code.startswith("CR-")
    assert report["title"] == "ದೊಡ್ಡ ಗುಂಡಿ (Severe pothole on 100ft road)"
    assert report["reported_severity"] == "severe"

    # 5. Check /me stats updated to 1
    me_res2 = client.get("/api/v1/auth/me", headers=auth_header)
    assert me_res2.status_code == 200
    stats = me_res2.get_json()["report_stats"]
    assert stats["total"] == 1
    assert stats["submitted"] == 1

    # 6. List user reports
    list_res = client.get("/api/v1/reports", headers=auth_header)
    assert list_res.status_code == 200
    list_data = list_res.get_json()
    assert list_data["total"] == 1
    assert list_data["items"][0]["reference_code"] == ref_code

    # 7. Get single report details
    single_res = client.get(f"/api/v1/reports/{report_id}", headers=auth_header)
    assert single_res.status_code == 200
    single_data = single_res.get_json()["report"]
    assert single_data["reference_code"] == ref_code
    assert single_data["latitude"] == pytest.approx(12.9719, abs=1e-4)

    # 8. Update profile
    prof_res = client.put(
        "/api/v1/auth/profile",
        json={
            "display_name": "Kavitha R. (Indiranagar Resident)",
            "preferred_language": "en",
        },
        headers=auth_header,
    )
    assert prof_res.status_code == 200
    prof_data = prof_res.get_json()["user"]
    assert prof_data["display_name"] == "Kavitha R. (Indiranagar Resident)"
    assert prof_data["preferred_language"] == "en"
