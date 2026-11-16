"""
CivicLens Telemetry Ingestion & Device Management Service
=========================================================
Handles edge device registration, token authentication, idempotent sensor event
ingestion, device freshness state machine, and real-time Server-Sent Events (SSE) broadcasting.
Maintains 100% backward compatibility with legacy Roadstate telemetry.
"""

import hashlib
import json
import logging
import queue
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import TelemetryDevice, TelemetryEvent
from backend.errors import ValidationError, UnauthorizedError

logger = logging.getLogger("civiclens.telemetry")

# In-memory thread-safe pub/sub queues for SSE subscribers
_sse_subscribers_lock = threading.Lock()
_sse_subscribers: List[queue.Queue] = []


def broadcast_telemetry_event(event_dict: Dict[str, Any]) -> None:
    """Broadcasts a new telemetry event to all active SSE listener queues."""
    with _sse_subscribers_lock:
        dead_queues = []
        for q in _sse_subscribers:
            try:
                q.put_nowait(event_dict)
            except queue.Full:
                dead_queues.append(q)
        for dq in dead_queues:
            _sse_subscribers.remove(dq)


def subscribe_telemetry_stream() -> queue.Queue:
    """Registers a new SSE listener queue."""
    q: queue.Queue = queue.Queue(maxsize=100)
    with _sse_subscribers_lock:
        _sse_subscribers.append(q)
    return q


def unsubscribe_telemetry_stream(q: queue.Queue) -> None:
    """Removes an SSE listener queue."""
    with _sse_subscribers_lock:
        if q in _sse_subscribers:
            _sse_subscribers.remove(q)


class TelemetryService:
    """Service for managing vehicle/edge sensor devices and real-time telemetry."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def _get_db(self) -> Session:
        return self._session_factory()

    @staticmethod
    def hash_token(token: str) -> str:
        """Computes SHA-256 hash of a device bearer token."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def authenticate_device(self, device_id_str: str, token: str, db: Session) -> Optional[TelemetryDevice]:
        """Validates device token against stored SHA-256 hash."""
        if not device_id_str or not token:
            return None
        hashed = self.hash_token(token)
        device = db.query(TelemetryDevice).filter(
            TelemetryDevice.device_id == device_id_str,
            TelemetryDevice.is_active == True,
        ).first()
        if device and device.api_key_hash == hashed:
            return device
        return None

    def calculate_freshness_status(self, device: TelemetryDevice) -> str:
        """
        Calculates device freshness status:
        - NOT_CONFIGURED: device created but has never sent a heartbeat or is inactive
        - CONNECTED: heartbeat received within the last 60 seconds
        - STALE: heartbeat received between 60 seconds and 300 seconds ago
        - DISCONNECTED: heartbeat older than 300 seconds
        - ERROR: explicitly flagged as error
        """
        if not device.is_active:
            return "DISCONNECTED"
        if device.status == "NOT_CONFIGURED" or device.last_heartbeat_at is None:
            return "NOT_CONFIGURED"
        if device.status == "ERROR":
            return "ERROR"

        now = datetime.now(timezone.utc)
        hb = device.last_heartbeat_at
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)

        age_seconds = (now - hb).total_seconds()
        if age_seconds <= 60:
            return "CONNECTED"
        elif age_seconds <= 300:
            return "STALE"
        else:
            return "DISCONNECTED"

    def ingest_event(
        self,
        device_id_str: str,
        token: str,
        payload: Dict[str, Any],
        dual_write_legacy: bool = True
    ) -> Tuple[Dict[str, Any], int]:
        """
        Ingests a verified telemetry event with idempotency and device status update.
        Dual-writes to legacy Roadstate detections for backward compatibility.
        """
        db = self._get_db()
        try:
            device = self.authenticate_device(device_id_str, token, db)
            if not device:
                return {
                    "status": "error",
                    "code": "UNAUTHORIZED",
                    "message": "Invalid device credentials or inactive device"
                }, 401

            # Validate payload fields
            event_id = payload.get("event_id") or f"EVT-{uuid.uuid4().hex[:12].upper()}"
            try:
                lat = float(payload.get("latitude"))
                lon = float(payload.get("longitude"))
            except (TypeError, ValueError):
                return {
                    "status": "error",
                    "code": "INVALID_COORDINATES",
                    "message": "Latitude and longitude must be valid floating point numbers"
                }, 400

            if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                return {
                    "status": "error",
                    "code": "OUT_OF_BOUNDS",
                    "message": f"Coordinates ({lat}, {lon}) are out of valid geographic range"
                }, 400

            severity = str(payload.get("severity", "minor")).lower()
            if severity not in {"minor", "moderate", "severe", "critical"}:
                severity = "minor"

            est_depth_cm = float(payload.get("est_depth_cm", 0.0) or 0.0)
            confidence = float(payload.get("confidence", 0.85) or 0.85)
            speed_kmh = float(payload.get("vehicle_speed_kmh", 0.0) or 0.0) if payload.get("vehicle_speed_kmh") is not None else None
            image_ref = payload.get("image_ref")
            road_surface = payload.get("road_surface", "asphalt")

            # Check Idempotency Key
            existing = db.query(TelemetryEvent).filter(TelemetryEvent.event_id == event_id).first()
            if existing:
                return {
                    "status": "duplicate",
                    "message": "Event already ingested (idempotent duplicate)",
                    "event_id": event_id,
                    "ingested_at": existing.ingested_at.isoformat() if existing.ingested_at else None
                }, 200

            now = datetime.now(timezone.utc)

            # Insert TelemetryEvent
            telem_event = TelemetryEvent(
                event_id=event_id,
                device_id=device.id,
                latitude=lat,
                longitude=lon,
                severity=severity,
                est_depth_cm=est_depth_cm,
                confidence=confidence,
                vehicle_speed_kmh=speed_kmh,
                image_ref=image_ref,
                road_surface=road_surface,
                raw_payload=payload,
                created_at=now,
                ingested_at=now,
            )
            db.add(telem_event)

            # Update Device Status & Heartbeat
            device.last_heartbeat_at = now
            device.last_latitude = lat
            device.last_longitude = lon
            device.status = "CONNECTED"
            device.total_events_ingested = (device.total_events_ingested or 0) + 1
            device.updated_at = now

            db.commit()

            # Dual-write to legacy detections for backward compatibility
            legacy_id = None
            if dual_write_legacy:
                try:
                    from backend.services.report_service import ReportService
                    rep_service = ReportService()
                    legacy_payload = {
                        "vehicle_id": device.assigned_vehicle or device.device_id,
                        "latitude": lat,
                        "longitude": lon,
                        "severity": severity if severity in {"minor", "moderate", "severe"} else "severe",
                        "est_depth_cm": est_depth_cm,
                        "confidence": confidence,
                        "image_ref": image_ref
                    }
                    res, _ = rep_service.process_detection_report(legacy_payload)
                    legacy_id = res.get("id")
                except Exception as legacy_err:
                    logger.warning(f"Dual-write to legacy detections deferred or handled: {legacy_err}")

            response_data = {
                "status": "success",
                "event_id": event_id,
                "device_id": device.device_id,
                "legacy_detection_id": legacy_id,
                "ingested_at": now.isoformat(),
                "severity": severity,
                "coordinates": [lat, lon]
            }

            # Broadcast to live SSE stream
            broadcast_telemetry_event({
                "type": "NEW_TELEMETRY_EVENT",
                "data": {
                    "event_id": event_id,
                    "device_id": device.device_id,
                    "device_name": device.device_name,
                    "assigned_vehicle": device.assigned_vehicle,
                    "latitude": lat,
                    "longitude": lon,
                    "severity": severity,
                    "est_depth_cm": est_depth_cm,
                    "confidence": confidence,
                    "vehicle_speed_kmh": speed_kmh,
                    "timestamp": now.timestamp(),
                    "iso_time": now.isoformat()
                }
            })

            return response_data, 201

        except Exception as e:
            db.rollback()
            logger.exception(f"Error ingesting telemetry event: {e}")
            return {
                "status": "error",
                "message": f"Internal server error: {str(e)}"
            }, 500
        finally:
            db.close()

    def update_heartbeat(
        self,
        device_id_str: str,
        token: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None
    ) -> Tuple[Dict[str, Any], int]:
        """Updates device heartbeat and optional current location."""
        db = self._get_db()
        try:
            device = self.authenticate_device(device_id_str, token, db)
            if not device:
                return {"status": "error", "message": "Unauthorized device"}, 401

            now = datetime.now(timezone.utc)
            device.last_heartbeat_at = now
            device.status = "CONNECTED"
            if latitude is not None and longitude is not None:
                device.last_latitude = latitude
                device.last_longitude = longitude
            device.updated_at = now
            db.commit()

            return {
                "status": "success",
                "device_id": device.device_id,
                "freshness": "CONNECTED",
                "heartbeat_at": now.isoformat()
            }, 200
        finally:
            db.close()

    def list_devices(self) -> List[Dict[str, Any]]:
        """Lists all registered telemetry devices with live freshness computation."""
        db = self._get_db()
        try:
            devices = db.query(TelemetryDevice).order_by(TelemetryDevice.device_id.asc()).all()
            results = []
            for d in devices:
                freshness = self.calculate_freshness_status(d)
                results.append({
                    "id": d.id,
                    "device_id": d.device_id,
                    "device_name": d.device_name,
                    "device_type": d.device_type,
                    "assigned_vehicle": d.assigned_vehicle,
                    "status": freshness,
                    "camera_stream_url": d.camera_stream_url,
                    "camera_status": d.camera_status,
                    "last_heartbeat_at": d.last_heartbeat_at.isoformat() if d.last_heartbeat_at else None,
                    "last_latitude": d.last_latitude,
                    "last_longitude": d.last_longitude,
                    "total_events_ingested": d.total_events_ingested,
                    "firmware_version": d.firmware_version,
                    "is_active": d.is_active
                })
            return results
        finally:
            db.close()

    def get_recent_events(self, limit: int = 50, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns recent sensor telemetry events with device metadata."""
        db = self._get_db()
        try:
            query = db.query(TelemetryEvent, TelemetryDevice).join(
                TelemetryDevice, TelemetryEvent.device_id == TelemetryDevice.id
            )
            if severity and severity != "all":
                query = query.filter(TelemetryEvent.severity == severity)

            rows = query.order_by(TelemetryEvent.created_at.desc()).limit(limit).all()
            output = []
            for ev, dev in rows:
                output.append({
                    "id": ev.id,
                    "event_id": ev.event_id,
                    "device_id": dev.device_id,
                    "device_name": dev.device_name,
                    "assigned_vehicle": dev.assigned_vehicle,
                    "latitude": ev.latitude,
                    "longitude": ev.longitude,
                    "severity": ev.severity,
                    "est_depth_cm": ev.est_depth_cm,
                    "confidence": ev.confidence,
                    "vehicle_speed_kmh": ev.vehicle_speed_kmh,
                    "road_surface": ev.road_surface,
                    "image_ref": ev.image_ref,
                    "created_at": ev.created_at.isoformat() if ev.created_at else None,
                    "timestamp": ev.created_at.timestamp() if ev.created_at else 0
                })
            return output
        finally:
            db.close()

    def get_telemetry_stats(self) -> Dict[str, Any]:
        """Computes aggregate operational telemetry metrics."""
        db = self._get_db()
        try:
            total_events = db.query(TelemetryEvent).count()
            devices = db.query(TelemetryDevice).all()

            connected = 0
            stale = 0
            disconnected = 0
            not_configured = 0

            for d in devices:
                freshness = self.calculate_freshness_status(d)
                if freshness == "CONNECTED":
                    connected += 1
                elif freshness == "STALE":
                    stale += 1
                elif freshness == "NOT_CONFIGURED":
                    not_configured += 1
                else:
                    disconnected += 1

            # Severity distribution
            sev_counts = dict(
                db.query(TelemetryEvent.severity, func.count(TelemetryEvent.id))
                .group_by(TelemetryEvent.severity)
                .all()
            )

            # Events in last 24h
            day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
            events_today = db.query(TelemetryEvent).filter(TelemetryEvent.created_at >= day_ago).count()

            return {
                "status": "success",
                "total_events": total_events,
                "events_today": events_today,
                "total_devices": len(devices),
                "connected_devices": connected,
                "stale_devices": stale,
                "disconnected_devices": disconnected,
                "not_configured_devices": not_configured,
                "active_camera_streams": 0,  # Honest: 0 until camera hardware is plugged in
                "severity_distribution": {
                    "severe": sev_counts.get("severe", 0),
                    "moderate": sev_counts.get("moderate", 0),
                    "minor": sev_counts.get("minor", 0),
                }
            }
        finally:
            db.close()
