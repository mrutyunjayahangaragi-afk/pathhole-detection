"""
Tests for Live Sensor Telemetry Ingestion, Device Registry & Freshness State Machine
====================================================================================
Validates edge device registration, token authentication, idempotent sensor ingestion,
device status transitions, and honest camera diagnostic reporting.
"""

import hashlib
import uuid
from datetime import datetime, timezone, timedelta
import pytest

from backend.db.engine import get_session_factory
from backend.db.models import TelemetryDevice, TelemetryEvent
from backend.services.telemetry_service import TelemetryService


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@pytest.fixture
def test_device(app):
    """Seeds an authorized edge device for testing."""
    with app.app_context():
        factory = get_session_factory()
        db = factory()
        try:
            dev_id = f"TEST-DEV-{uuid.uuid4().hex[:6].upper()}"
            device = TelemetryDevice(
                device_id=dev_id,
                device_name="Test Patrol Unit",
                device_type="vehicle_edge",
                assigned_vehicle="KA-01-TEST",
                api_key_hash=_hash("secret_token_123"),
                status="CONNECTED",
                camera_status="not_configured",
                last_heartbeat_at=datetime.now(timezone.utc),
                last_latitude=12.9716,
                last_longitude=77.5946,
                total_events_ingested=0,
                firmware_version="v2.4.0-edge"
            )
            db.add(device)
            db.commit()
            db.refresh(device)
            return {"device_id": dev_id, "token": "secret_token_123", "id": device.id}
        finally:
            db.close()


def test_device_authentication_valid_and_invalid(app, test_device):
    """Scenario: Valid token authenticates; invalid token is rejected."""
    with app.app_context():
        service = TelemetryService()
        db = get_session_factory()()
        try:
            # Valid
            dev = service.authenticate_device(test_device["device_id"], test_device["token"], db)
            assert dev is not None
            assert dev.device_id == test_device["device_id"]

            # Invalid token
            dev_bad = service.authenticate_device(test_device["device_id"], "wrong_token", db)
            assert dev_bad is None

            # Unknown device
            dev_unknown = service.authenticate_device("UNKNOWN-DEV", "secret_token_123", db)
            assert dev_unknown is None
        finally:
            db.close()


def test_device_freshness_state_machine():
    """Scenario: Freshness transitions correctly between CONNECTED, STALE, DISCONNECTED, NOT_CONFIGURED."""
    service = TelemetryService()
    now = datetime.now(timezone.utc)

    # 1. Connected (<= 60 seconds)
    dev_connected = TelemetryDevice(
        device_id="DEV-CONN",
        device_name="Connected Dev",
        api_key_hash="hash",
        status="CONNECTED",
        last_heartbeat_at=now - timedelta(seconds=20),
        is_active=True
    )
    assert service.calculate_freshness_status(dev_connected) == "CONNECTED"

    # 2. Stale (60s to 300s)
    dev_stale = TelemetryDevice(
        device_id="DEV-STALE",
        device_name="Stale Dev",
        api_key_hash="hash",
        status="CONNECTED",
        last_heartbeat_at=now - timedelta(seconds=120),
        is_active=True
    )
    assert service.calculate_freshness_status(dev_stale) == "STALE"

    # 3. Disconnected (> 300s)
    dev_disc = TelemetryDevice(
        device_id="DEV-DISC",
        device_name="Disconnected Dev",
        api_key_hash="hash",
        status="CONNECTED",
        last_heartbeat_at=now - timedelta(seconds=600),
        is_active=True
    )
    assert service.calculate_freshness_status(dev_disc) == "DISCONNECTED"

    # 4. Not Configured (no heartbeat)
    dev_unconf = TelemetryDevice(
        device_id="DEV-UNCONF",
        device_name="Unconfigured Dev",
        api_key_hash="hash",
        status="NOT_CONFIGURED",
        last_heartbeat_at=None,
        is_active=True
    )
    assert service.calculate_freshness_status(dev_unconf) == "NOT_CONFIGURED"


def test_telemetry_event_ingestion_and_idempotency(client, test_device):
    """Scenario: Authorized sensor telemetry ingest succeeds; duplicate event_id is idempotent."""
    event_id = f"EVT-IDEMP-{uuid.uuid4().hex[:8].upper()}"
    payload = {
        "device_id": test_device["device_id"],
        "token": test_device["token"],
        "event_id": event_id,
        "latitude": 12.9750,
        "longitude": 77.5920,
        "severity": "severe",
        "est_depth_cm": 4.5,
        "confidence": 0.91,
        "vehicle_speed_kmh": 32.5
    }

    # First ingestion -> 201 Created
    res1 = client.post("/api/v1/telemetry/ingest", json=payload)
    assert res1.status_code == 201
    data1 = res1.get_json()
    assert data1["status"] == "success"
    assert data1["event_id"] == event_id
    assert data1["severity"] == "severe"

    # Duplicate ingestion -> 200 OK (idempotent duplicate)
    res2 = client.post("/api/v1/telemetry/ingest", json=payload)
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2["status"] == "duplicate"
    assert data2["event_id"] == event_id


def test_telemetry_unauthorized_and_invalid_bounds(client, test_device):
    """Scenario: Missing credentials return 401; out of range coordinates return 400."""
    # 401 on missing token
    res_no_tok = client.post("/api/v1/telemetry/ingest", json={
        "device_id": test_device["device_id"],
        "latitude": 12.97,
        "longitude": 77.59
    })
    assert res_no_tok.status_code == 401

    # 401 on bad token
    res_bad_tok = client.post("/api/v1/telemetry/ingest", json={
        "device_id": test_device["device_id"],
        "token": "invalid_token_xyz",
        "latitude": 12.97,
        "longitude": 77.59
    })
    assert res_bad_tok.status_code == 401

    # 400 on out-of-bounds latitude
    res_out_lat = client.post("/api/v1/telemetry/ingest", json={
        "device_id": test_device["device_id"],
        "token": test_device["token"],
        "latitude": 95.5,
        "longitude": 77.59
    })
    assert res_out_lat.status_code == 400
    assert res_out_lat.get_json()["code"] == "OUT_OF_BOUNDS"


def test_device_heartbeat_api(client, test_device):
    """Scenario: Edge device updates heartbeat and coordinates."""
    res = client.post("/api/v1/telemetry/heartbeat", json={
        "device_id": test_device["device_id"],
        "token": test_device["token"],
        "latitude": 12.9780,
        "longitude": 77.5960
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["freshness"] == "CONNECTED"


def test_list_devices_and_stats(client, test_device):
    """Scenario: Public endpoints list fleet devices and operational statistics."""
    res_dev = client.get("/api/v1/telemetry/devices")
    assert res_dev.status_code == 200
    dev_data = res_dev.get_json()
    assert dev_data["status"] == "success"
    assert dev_data["count"] >= 1
    found = any(d["device_id"] == test_device["device_id"] for d in dev_data["devices"])
    assert found is True

    res_stats = client.get("/api/v1/telemetry/stats")
    assert res_stats.status_code == 200
    stat_data = res_stats.get_json()
    assert stat_data["status"] == "success"
    assert "total_events" in stat_data
    assert "connected_devices" in stat_data
    assert stat_data["active_camera_streams"] == 0  # Honest offline state


def test_honest_camera_endpoint(client, test_device):
    """Scenario: Camera stream endpoint honestly reports not_configured rather than mock video."""
    res = client.get(f"/api/v1/telemetry/camera/{test_device['device_id']}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "not_configured"
    assert data["device_id"] == test_device["device_id"]
    assert "camera_status" in data
    assert "not currently active" in data["message"]

    # Unknown device returns 404
    res_unk = client.get("/api/v1/telemetry/camera/NONEXISTENT-DEV")
    assert res_unk.status_code == 404
