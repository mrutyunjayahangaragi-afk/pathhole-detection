"""
Telemetry Repository
====================
Persistence operations for Roadstate IoT edge telemetry devices and detection events.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.db.models import TelemetryDevice, TelemetryEvent


class TelemetryRepository:
    def __init__(self, session: Session):
        self.session = session

    def register_device(self, data: Dict[str, Any]) -> TelemetryDevice:
        """Registers or updates a vehicle sensor unit."""
        device = self.session.query(TelemetryDevice).filter_by(device_id=data.get("device_id")).first()
        if device:
            for k, v in data.items():
                setattr(device, k, v)
        else:
            device = TelemetryDevice(**data)
            self.session.add(device)
        self.session.flush()
        return device

    def get_device_by_id(self, device_id: str) -> Optional[TelemetryDevice]:
        """Retrieves a device by its physical device ID."""
        return self.session.query(TelemetryDevice).filter_by(device_id=device_id).first()

    def list_active_devices(self) -> List[TelemetryDevice]:
        """Lists all registered telemetry devices."""
        return self.session.query(TelemetryDevice).order_by(TelemetryDevice.last_heartbeat.desc()).all()

    def record_event(self, data: Dict[str, Any]) -> TelemetryEvent:
        """Persists a new telemetry detection event."""
        event = TelemetryEvent(**data)
        self.session.add(event)
        self.session.flush()
        return event

    def get_recent_events(self, limit: int = 50) -> List[TelemetryEvent]:
        """Retrieves the newest incoming telemetry events."""
        return (
            self.session.query(TelemetryEvent)
            .order_by(TelemetryEvent.created_at.desc())
            .limit(limit)
            .all()
        )
