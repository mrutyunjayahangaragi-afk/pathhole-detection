"""
Database Health Service
=======================
Service layer for application readiness, liveness probes, and platform diagnostics.
"""

from typing import Dict, Any, Optional
import time

from backend.config import get_config
from backend.database.health import check_db_connectivity, get_database_metrics
from backend.services.storage_service import StorageService


class DatabaseHealthService:
    def __init__(self, config=None):
        self.cfg = config or get_config()
        self.storage_service = StorageService(self.cfg)

    def get_liveness(self) -> Dict[str, Any]:
        """Kubernetes/Platform liveness check — confirms the process is alive."""
        return {
            "status": "ok",
            "timestamp": time.time(),
        }

    def get_readiness(self) -> Dict[str, Any]:
        """Readiness probe — confirms database is reachable and schema tables exist."""
        metrics = get_database_metrics()
        is_ready = metrics.get("ready", False) and metrics.get("health", {}).get("connected", False)
        return {
            "status": "ready" if is_ready else "degraded",
            "database_ready": is_ready,
            "provider": metrics.get("health", {}).get("provider"),
            "latency_ms": metrics.get("health", {}).get("latency_ms"),
            "table_count": metrics.get("table_count"),
        }

    def get_database_diagnostics(self) -> Dict[str, Any]:
        """Full system diagnostics without leaking credentials."""
        metrics = get_database_metrics()
        storage_available = self.storage_service.is_storage_available()
        return {
            "status": "success",
            "database": {
                "provider": metrics.get("health", {}).get("provider"),
                "connected": metrics.get("health", {}).get("connected"),
                "latency_ms": metrics.get("health", {}).get("latency_ms"),
                "table_count": metrics.get("table_count"),
                "ready": metrics.get("ready"),
            },
            "storage": {
                "available": storage_available,
                "provider": "supabase" if storage_available else "local",
                "buckets_configured": [
                    "citizen-evidence",
                    "inspection-evidence",
                    "resolution-evidence",
                    "telemetry-evidence",
                    "profile-avatars",
                ],
            },
            "auth": {
                "provider": "supabase",
                "google_oauth_configured": bool(getattr(self.cfg, "SUPABASE_URL", None) and getattr(self.cfg, "SUPABASE_PUBLISHABLE_KEY", None)),
            },
        }
