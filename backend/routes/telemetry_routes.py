"""
CivicLens Telemetry API Blueprint & Routes
==========================================
Endpoints for device authentication, idempotent sensor telemetry ingestion,
device fleet status, recent events, operational stats, and SSE streaming.
"""

import json
import logging
import queue
import time
from typing import Generator
from flask import Blueprint, request, jsonify, Response, current_app

from backend.services.telemetry_service import (
    TelemetryService,
    subscribe_telemetry_stream,
    unsubscribe_telemetry_stream,
)

logger = logging.getLogger("civiclens.telemetry_routes")

telemetry_bp = Blueprint("telemetry_bp", __name__, url_prefix="/api/v1/telemetry")


def _extract_auth(req) -> tuple:
    """Extracts device_id and token from headers or JSON body."""
    auth_header = req.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif req.headers.get("X-Device-Token"):
        token = req.headers.get("X-Device-Token").strip()

    device_id = req.headers.get("X-Device-Id", "").strip()

    data = req.get_json(force=True, silent=True) or {}
    if not token and "token" in data:
        token = str(data.get("token")).strip()
    if not device_id and "device_id" in data:
        device_id = str(data.get("device_id")).strip()

    return device_id, token, data


@telemetry_bp.route("/ingest", methods=["POST"])
def ingest_telemetry():
    """
    Ingests sensor telemetry report from an authorized edge device or vehicle.
    Supports token auth and idempotent deduplication via event_id.
    """
    device_id, token, data = _extract_auth(request)
    if not device_id or not token:
        return jsonify({
            "status": "error",
            "code": "MISSING_CREDENTIALS",
            "message": "Both device_id and device token are required (via headers or body)"
        }), 401

    service = TelemetryService()
    result, status_code = service.ingest_event(device_id, token, data)
    return jsonify(result), status_code


@telemetry_bp.route("/heartbeat", methods=["POST"])
def device_heartbeat():
    """Heartbeat endpoint for edge devices to report online status and coordinates."""
    device_id, token, data = _extract_auth(request)
    if not device_id or not token:
        return jsonify({
            "status": "error",
            "message": "device_id and token required"
        }), 401

    lat = data.get("latitude")
    lon = data.get("longitude")
    service = TelemetryService()
    result, status_code = service.update_heartbeat(device_id, token, lat, lon)
    return jsonify(result), status_code


@telemetry_bp.route("/devices", methods=["GET"])
def list_telemetry_devices():
    """Returns the fleet of registered telemetry devices with live freshness status."""
    service = TelemetryService()
    devices = service.list_devices()
    return jsonify({
        "status": "success",
        "count": len(devices),
        "devices": devices
    }), 200


@telemetry_bp.route("/events/recent", methods=["GET"])
def get_recent_telemetry_events():
    """Returns recent telemetry events, optionally filtered by severity."""
    limit = request.args.get("limit", 50)
    try:
        limit = min(max(int(limit), 1), 200)
    except ValueError:
        limit = 50

    severity = request.args.get("severity")
    service = TelemetryService()
    events = service.get_recent_events(limit=limit, severity=severity)
    return jsonify({
        "status": "success",
        "count": len(events),
        "events": events
    }), 200


@telemetry_bp.route("/stats", methods=["GET"])
def get_telemetry_statistics():
    """Returns aggregate operational statistics for edge devices and events."""
    service = TelemetryService()
    stats = service.get_telemetry_stats()
    return jsonify(stats), 200


@telemetry_bp.route("/camera/<device_id>", methods=["GET"])
def get_camera_feed(device_id):
    """
    Honest camera stream endpoint.
    Explicitly reports 'not_configured' or 'offline' instead of mocking moving video.
    """
    service = TelemetryService()
    devices = service.list_devices()
    match = next((d for d in devices if d["device_id"] == device_id), None)
    if not match:
        return jsonify({
            "status": "error",
            "code": "DEVICE_NOT_FOUND",
            "message": f"No device registered with ID {device_id}"
        }), 404

    return jsonify({
        "status": "not_configured",
        "device_id": match["device_id"],
        "device_name": match["device_name"],
        "camera_status": match["camera_status"],
        "message": "Video streaming pipeline is not currently active for this edge device. Live GPS coordinates and telemetry metadata are active.",
        "documentation": "Connect RTSP or WebRTC stream to enable live optical feed."
    }), 200


@telemetry_bp.route("/stream", methods=["GET"])
def telemetry_sse_stream():
    """
    Server-Sent Events (SSE) real-time streaming endpoint for the Live Monitor.
    Pushes new telemetry events as they arrive, and emits periodic heartbeats.
    """
    def event_stream() -> Generator[str, None, None]:
        q = subscribe_telemetry_stream()
        try:
            # Send initial connection confirmation
            yield f"event: connected\ndata: {json.dumps({'message': 'Connected to CivicLens Live Telemetry Stream'})}\n\n"
            
            while True:
                try:
                    # Wait up to 15 seconds for a new event
                    event_data = q.get(timeout=15.0)
                    yield f"event: telemetry\ndata: {json.dumps(event_data)}\n\n"
                except queue.Empty:
                    # Emit SSE comment ping to keep connection alive
                    yield ": ping\n\n"
        except GeneratorExit:
            unsubscribe_telemetry_stream(q)
        finally:
            unsubscribe_telemetry_stream(q)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
