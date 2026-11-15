"""
Baseline REST API Test Suite
============================

Verifies existing application functionality remains operational (Rule 6)
and that invalid API input receives appropriate structured responses (Rule 8).
"""

import pytest


def test_health_endpoint(client):
    """Rule 6: Health check endpoint returns operational status and diagnostics."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "version" in data


def test_cors_preflight(client):
    """Rule 6: CORS preflight OPTIONS request succeeds with 204."""
    res = client.open("/api/detections", method="OPTIONS")
    assert res.status_code == 204
    assert res.headers.get("Access-Control-Allow-Origin") is not None


def test_submit_new_and_merged_detections(client, clean_db):
    """
    Rule 6: Submission of fresh detections and subsequent duplicate merge within 15m.
    """
    # 1. Submit first detection -> Expected 201 (new)
    payload_1 = {
        "vehicle_id": "bus-001",
        "latitude": 8.52410,
        "longitude": 76.93660,
        "severity": "minor",
        "est_depth_cm": 1.5,
        "confidence": 0.82,
        "image_ref": "s3://civiclens/frame1.jpg",
    }
    res_1 = client.post("/api/detections", json=payload_1)
    assert res_1.status_code == 201
    data_1 = res_1.get_json()
    assert data_1["merged"] is False
    det_id = data_1["detection"]["id"]
    assert data_1["detection"]["report_count"] == 1
    assert data_1["detection"]["severity"] == "minor"

    # 2. Submit second detection 5m away -> Expected 200 (merged)
    # 5 meters is roughly 0.000045 degrees latitude
    payload_2 = {
        "vehicle_id": "car-012",
        "latitude": 8.52414,
        "longitude": 76.93660,
        "severity": "severe",
        "est_depth_cm": 6.2,
        "confidence": 0.91,
    }
    res_2 = client.post("/api/detections", json=payload_2)
    assert res_2.status_code == 200
    data_2 = res_2.get_json()
    assert data_2["merged"] is True
    assert data_2["detection"]["id"] == det_id
    assert data_2["detection"]["report_count"] == 2
    assert data_2["detection"]["severity"] == "severe"  # Elevated to worse severity
    assert data_2["detection"]["est_depth_cm"] == 6.2

    # 3. Submit third detection far away (150m away) -> Expected 201 (distinct new)
    payload_3 = {
        "vehicle_id": "bus-003",
        "latitude": 8.52550,
        "longitude": 76.93660,
        "severity": "moderate",
        "est_depth_cm": 3.0,
    }
    res_3 = client.post("/api/detections", json=payload_3)
    assert res_3.status_code == 201
    data_3 = res_3.get_json()
    assert data_3["merged"] is False
    assert data_3["detection"]["id"] != det_id


def test_list_and_get_detections(client, clean_db):
    """Rule 6: List detections with pagination, filtering, and retrieval by ID."""
    # Seed two detections
    client.post("/api/detections", json={
        "vehicle_id": "bus-001", "latitude": 8.51, "longitude": 76.91, "severity": "minor"
    })
    post_res = client.post("/api/detections", json={
        "vehicle_id": "bus-002", "latitude": 8.55, "longitude": 76.95, "severity": "severe"
    })
    det_id = post_res.get_json()["detection"]["id"]

    # List all
    list_res = client.get("/api/detections")
    assert list_res.status_code == 200
    items = list_res.get_json()
    assert len(items) == 2

    # Filter by severity
    filter_res = client.get("/api/detections?severity=severe")
    assert filter_res.status_code == 200
    filtered = filter_res.get_json()
    assert len(filtered) == 1
    assert filtered[0]["id"] == det_id

    # Get single by ID
    single_res = client.get(f"/api/detections/{det_id}")
    assert single_res.status_code == 200
    assert single_res.get_json()["id"] == det_id


def test_patch_detection_status(client, clean_db):
    """Rule 6: Municipal status progression updates status cleanly."""
    post_res = client.post("/api/detections", json={
        "vehicle_id": "bus-001", "latitude": 8.52, "longitude": 76.92, "severity": "moderate"
    })
    det_id = post_res.get_json()["detection"]["id"]

    patch_res = client.patch(f"/api/detections/{det_id}", json={"status": "acknowledged"})
    assert patch_res.status_code == 200
    assert patch_res.get_json()["status"] == "acknowledged"

    # Progress to repaired
    repaired_res = client.patch(f"/api/detections/{det_id}", json={"status": "repaired"})
    assert repaired_res.status_code == 200
    assert repaired_res.get_json()["status"] == "repaired"


def test_stats_endpoint(client, clean_db):
    """Rule 6: Stats aggregation matches database state."""
    client.post("/api/detections", json={
        "vehicle_id": "bus-001", "latitude": 8.52, "longitude": 76.92, "severity": "minor"
    })
    client.post("/api/detections", json={
        "vehicle_id": "car-002", "latitude": 8.53, "longitude": 76.93, "severity": "severe"
    })

    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.get_json()
    assert data["total_reports"] == 2
    assert data["active_vehicles"] == 2
    assert data["open_by_severity"]["minor"] == 1
    assert data["open_by_severity"]["severe"] == 1


# ---------------------------------------------------------------------------
# Rule 8: Invalid API Input Receives Appropriate Response
# ---------------------------------------------------------------------------

def test_missing_required_fields_returns_400(client, clean_db):
    """Rule 8: Missing required payload fields returns HTTP 400."""
    res = client.post("/api/detections", json={"latitude": 8.52})
    assert res.status_code == 400
    data = res.get_json()
    assert "error" in data
    assert "Missing required fields" in data["error"]


def test_invalid_severity_returns_400(client, clean_db):
    """Rule 8: Invalid severity value returns HTTP 400."""
    payload = {
        "vehicle_id": "bus-001",
        "latitude": 8.52,
        "longitude": 76.92,
        "severity": "catastrophic",  # Invalid
    }
    res = client.post("/api/detections", json=payload)
    assert res.status_code == 400
    assert "severity must be one of" in res.get_json()["error"]


def test_invalid_coordinates_returns_400(client, clean_db):
    """Rule 8: Non-numeric or out-of-range coordinates return HTTP 400."""
    # Non-numeric
    res_1 = client.post("/api/detections", json={
        "vehicle_id": "bus-001", "latitude": "invalid", "longitude": 76.92, "severity": "minor"
    })
    assert res_1.status_code == 400

    # Latitude out of range (> 90)
    res_2 = client.post("/api/detections", json={
        "vehicle_id": "bus-001", "latitude": 95.0, "longitude": 76.92, "severity": "minor"
    })
    assert res_2.status_code == 400
    assert "Latitude 95.0 out of valid range" in res_2.get_json()["error"]


def test_nonexistent_detection_returns_404(client, clean_db):
    """Rule 8: Querying or updating a non-existent detection ID returns HTTP 404."""
    get_res = client.get("/api/detections/non-existent-uuid")
    assert get_res.status_code == 404

    patch_res = client.patch("/api/detections/non-existent-uuid", json={"status": "acknowledged"})
    assert patch_res.status_code == 404


def test_patch_invalid_status_returns_400(client, clean_db):
    """Rule 8: Patching an invalid status returns HTTP 400."""
    post_res = client.post("/api/detections", json={
        "vehicle_id": "bus-001", "latitude": 8.52, "longitude": 76.92, "severity": "minor"
    })
    det_id = post_res.get_json()["detection"]["id"]

    patch_res = client.patch(f"/api/detections/{det_id}", json={"status": "invalid_status"})
    assert patch_res.status_code == 400


def test_frontend_and_dashboard_routes(client):
    """Verifies portal home, responsive dashboard, and static assets are served."""
    res_home = client.get("/")
    assert res_home.status_code == 200
    assert b"CivicLens" in res_home.data

    res_dash = client.get("/dashboard")
    assert res_dash.status_code == 200
    assert b"CivicLens" in res_dash.data

    res_css = client.get("/static/css/civiclens.css")
    assert res_css.status_code == 200
    assert b"CivicLens" in res_css.data

    res_js = client.get("/static/js/nav.js")
    assert res_js.status_code == 200

    res_citizen = client.get("/frontend/citizen-report.html")
    assert res_citizen.status_code == 200
    assert b"CivicLens" in res_citizen.data

