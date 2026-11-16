"""
Centralized Configuration Module for CivicLens / Roadstate
============================================================

Supports environment-variable based configuration for Development, Testing,
and Production environments, with safe defaults and robust path resolution.
"""

import os
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv
    # Load .env file from project root or backend folder if present
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()
except ImportError:
    pass  # python-dotenv is optional; fallback to os.environ directly


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


class ConfigurationError(ValueError):
    """Raised when application configuration is missing, invalid, or unsafe."""
    pass


def _bool_from_env(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def redact_secret(val: Optional[str], show_chars: int = 4) -> str:
    """Safely redacts secrets for logs and reports without exposing private data."""
    if not val:
        return "[NOT SET]"
    trimmed = str(val).strip()
    if len(trimmed) <= show_chars * 2:
        return "[REDACTED]"
    return f"{trimmed[:show_chars]}...{trimmed[-show_chars:]} (len={len(trimmed)})"


def normalize_database_url(url: Optional[str]) -> Optional[str]:
    """
    Normalizes PostgreSQL database URLs for SQLAlchemy compatibility.
    - Normalizes `postgres://` to `postgresql://`
    - Ensures `sslmode=require` for remote hosts (e.g. Supabase poolers)
    """
    if not url:
        return url
    trimmed = url.strip()
    if trimmed.startswith("postgres://"):
        trimmed = "postgresql://" + trimmed[len("postgres://"):]

    # Enforce sslmode=require for remote hosts unless already set or local
    if trimmed.startswith("postgresql"):
        lower = trimmed.lower()
        if "sslmode=" not in lower and "localhost" not in lower and "127.0.0.1" not in lower:
            delim = "&" if "?" in trimmed else "?"
            trimmed = f"{trimmed}{delim}sslmode=require"

    return trimmed


def _resolve_db_path(raw_path: str) -> str:
    """
    Safely resolves SQLite database paths regardless of the current working directory.
    If an in-memory database or absolute path is provided, it is returned as-is.
    If a relative path is provided, it checks PROJECT_ROOT and BASE_DIR.
    """
    if raw_path == ":memory:":
        return ":memory:"
    
    path_obj = Path(raw_path)
    if path_obj.is_absolute():
        return str(path_obj)
    
    # Check if relative to project root
    candidate_root = PROJECT_ROOT / path_obj
    if candidate_root.exists():
        return str(candidate_root)
        
    # Check if relative to backend folder
    candidate_backend = BASE_DIR / path_obj
    if candidate_backend.exists():
        return str(candidate_backend)
        
    # Default to placing it in backend/ if it doesn't exist yet
    return str(candidate_root if path_obj.parts[0] == "backend" else candidate_backend)


class Config:
    """Base application configuration."""
    def __init__(self):
        # Support modern APP_ENV, with backward-compatible FLASK_ENV fallback
        self.ENV = (
            os.environ.get("APP_ENV") or
            os.environ.get("FLASK_ENV") or
            os.environ.get("ENVIRONMENT") or
            "development"
        ).lower().strip()
        self.DEBUG = _bool_from_env("FLASK_DEBUG", False)
        self.TESTING = False
        
        self.HOST = os.environ.get("HOST", "127.0.0.1")
        try:
            self.PORT = int(os.environ.get("PORT", "5055"))
            if not (1 <= self.PORT <= 65535):
                raise ConfigurationError(f"PORT must be between 1 and 65535, got {self.PORT}")
        except ValueError as e:
            raise ConfigurationError(f"Invalid PORT value: {e}") from e

        self.SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-dev-key-civiclens-change-in-production")
        
        # Database Provider: 'sqlite', 'supabase', or 'postgresql'
        self.DATABASE_PROVIDER = os.environ.get("DATABASE_PROVIDER", "sqlite").lower().strip()
        if self.DATABASE_PROVIDER not in ("sqlite", "supabase", "postgresql"):
            raise ConfigurationError(
                f"Unsupported DATABASE_PROVIDER '{self.DATABASE_PROVIDER}'. Must be 'sqlite', 'supabase', or 'postgresql'."
            )

        raw_url = os.environ.get("DATABASE_URL")
        self.SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
        self.SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()

        if self.DATABASE_PROVIDER in ("supabase", "postgresql"):
            # Strict safety check: Never silently fall back to SQLite when Supabase is requested!
            if not raw_url or not raw_url.strip():
                raise ConfigurationError(
                    f"DATABASE_PROVIDER is set to '{self.DATABASE_PROVIDER}', but DATABASE_URL is missing or empty. "
                    "Configure your Supabase PostgreSQL connection string in .env (e.g. DATABASE_URL=postgresql://postgres:...@...)."
                )
            if "YOUR_SUPABASE" in raw_url or "[password]" in raw_url or "YOUR_PASSWORD" in raw_url:
                raise ConfigurationError(
                    "DATABASE_URL contains placeholder values. Please replace with your actual Supabase PostgreSQL connection string in .env."
                )
            self.DATABASE_URL = normalize_database_url(raw_url)
            self.RAW_DB_PATH = None
            self.DATABASE_PATH = None
        else:
            self.RAW_DB_PATH = os.environ.get("DATABASE_PATH", "backend/pothole_reports.db")
            self.DATABASE_PATH = _resolve_db_path(self.RAW_DB_PATH)
            self.DATABASE_URL = f"sqlite:///{self.DATABASE_PATH}"
        
        # Deduplication
        try:
            self.DEDUP_RADIUS_METERS = float(os.environ.get("DEDUP_RADIUS_METERS", "15.0"))
            if self.DEDUP_RADIUS_METERS <= 0:
                raise ConfigurationError("DEDUP_RADIUS_METERS must be greater than 0")
        except ValueError as e:
            raise ConfigurationError(f"Invalid DEDUP_RADIUS_METERS: {e}") from e

        # Geolocation / Nominatim
        self.NOMINATIM_USER_AGENT = os.environ.get(
            "NOMINATIM_USER_AGENT", "CivicLens-Infrastructure/1.0 (civic-triage-demo)"
        )
        try:
            self.NOMINATIM_RATE_LIMIT_SECONDS = float(os.environ.get("NOMINATIM_RATE_LIMIT_SECONDS", "1.0"))
            if self.NOMINATIM_RATE_LIMIT_SECONDS < 0:
                raise ConfigurationError("NOMINATIM_RATE_LIMIT_SECONDS cannot be negative")
        except ValueError as e:
            raise ConfigurationError(f"Invalid NOMINATIM_RATE_LIMIT_SECONDS: {e}") from e

        # CORS
        raw_cors = os.environ.get("CORS_ORIGINS", "http://localhost:5055,http://127.0.0.1:5055")
        self.CORS_ORIGINS: List[str] = [
            o.strip() for o in raw_cors.split(",") if o.strip()
        ]

        # Logging
        self.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

        # Uploads
        self.UPLOAD_FOLDER = str(PROJECT_ROOT / os.environ.get("UPLOAD_FOLDER", "uploads"))
        try:
            max_mb = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "16"))
            if max_mb <= 0:
                raise ConfigurationError("MAX_CONTENT_LENGTH_MB must be greater than 0")
            self.MAX_CONTENT_LENGTH_MB = max_mb
            self.MAX_CONTENT_LENGTH = max_mb * 1024 * 1024
        except ValueError as e:
            raise ConfigurationError(f"Invalid MAX_CONTENT_LENGTH_MB: {e}") from e

        # AI Defect Detection Configuration
        self.MODEL_NAME = os.environ.get("MODEL_NAME", "yolov8-pothole")
        self.MODEL_VERSION = os.environ.get("MODEL_VERSION", "v1.0.0")
        raw_weights = os.environ.get("MODEL_WEIGHTS_PATH", "weights/pothole_yolov8.pt")
        self.MODEL_WEIGHTS_PATH = str(PROJECT_ROOT / raw_weights) if raw_weights else None
        try:
            self.CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.40"))
            self.HIGH_CONFIDENCE_THRESHOLD = float(os.environ.get("HIGH_CONFIDENCE_THRESHOLD", "0.75"))
            self.IOU_THRESHOLD = float(os.environ.get("IOU_THRESHOLD", "0.45"))
        except ValueError as e:
            raise ConfigurationError(f"Invalid detection threshold configuration: {e}") from e
        self.AUTO_DETECT_ON_SUBMISSION = _bool_from_env("AUTO_DETECT_ON_SUBMISSION", True)

        # Map Tiles & Centralized Provider Configuration
        self.MAP_TILE_PROVIDER = os.environ.get("MAP_TILE_PROVIDER", "carto").strip().lower()
        self.CARTO_BASEMAP_STYLE = os.environ.get("CARTO_BASEMAP_STYLE", "voyager").strip().lower()
        self.CARTO_BASEMAP_API_KEY = os.environ.get(
            "CARTO_BASEMAP_API_KEY", os.environ.get("CARTO_API_KEY", "")
        ).strip()
        self.CARTO_API_KEY = self.CARTO_BASEMAP_API_KEY  # Backward-compatibility alias
        self.ALLOW_OSM_DEV_FALLBACK = _bool_from_env("ALLOW_OSM_DEV_FALLBACK", True)

        # Supabase API & Auth Configuration
        self.SUPABASE_PUBLISHABLE_KEY = os.environ.get(
            "SUPABASE_PUBLISHABLE_KEY", os.environ.get("SUPABASE_ANON_KEY", "")
        ).strip()
        self.SUPABASE_ANON_KEY = self.SUPABASE_PUBLISHABLE_KEY  # Alias
        self.SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

        # Duplicate Incident Matching Configuration
        self.DUPLICATE_MATCHING_ENABLED = _bool_from_env("DUPLICATE_MATCHING_ENABLED", True)
        self.DUPLICATE_AUTO_LINK_ENABLED = _bool_from_env("DUPLICATE_AUTO_LINK_ENABLED", False)
        self.DUPLICATE_REQUIRE_HUMAN_REVIEW = _bool_from_env("DUPLICATE_REQUIRE_HUMAN_REVIEW", True)

        # Public Map & Viewport Query Configuration
        try:
            self.PUBLIC_MAP_DEFAULT_RADIUS_KM = float(os.environ.get("PUBLIC_MAP_DEFAULT_RADIUS_KM", "25.0"))
            self.PUBLIC_MAP_MAX_VIEWPORT_POINTS = int(os.environ.get("PUBLIC_MAP_MAX_VIEWPORT_POINTS", "500"))
        except ValueError as e:
            raise ConfigurationError(f"Invalid public map configuration: {e}") from e

        # Notification System Configuration
        self.NOTIFICATION_PROVIDER_EMAIL = os.environ.get("NOTIFICATION_PROVIDER_EMAIL", "console").strip().lower()
        self.SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
        try:
            self.SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
        except ValueError:
            self.SMTP_PORT = 587
        self.SMTP_USER = os.environ.get("SMTP_USER", "").strip()
        self.SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
        self.SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "notifications@civiclens.org").strip()

        self.NOTIFICATION_PROVIDER_SMS = os.environ.get("NOTIFICATION_PROVIDER_SMS", "console").strip().lower()
        self.TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
        self.TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
        self.TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "").strip()

        self.NOTIFICATION_PROVIDER_WHATSAPP = os.environ.get("NOTIFICATION_PROVIDER_WHATSAPP", "disabled").strip().lower()
        self.META_WHATSAPP_TOKEN = os.environ.get("META_WHATSAPP_TOKEN", "").strip()
        self.META_WHATSAPP_PHONE_ID = os.environ.get("META_WHATSAPP_PHONE_ID", "").strip()

        self.NOTIFICATION_PROVIDER_PUSH = os.environ.get("NOTIFICATION_PROVIDER_PUSH", "disabled").strip().lower()
        self.VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
        self.VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
        self.VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "admin@civiclens.org").strip()


class DevelopmentConfig(Config):
    """Development environment configuration."""
    def __init__(self):
        super().__init__()
        self.DEBUG = True


class TestingConfig(Config):
    """Testing environment configuration."""
    __test__ = False  # Prevent pytest from treating this configuration as a test suite
    def __init__(self):
        # Prevent test suite from failing if developer has DATABASE_PROVIDER=supabase in local .env
        orig_provider = os.environ.get("DATABASE_PROVIDER")
        try:
            os.environ["DATABASE_PROVIDER"] = "sqlite"
            super().__init__()
        finally:
            if orig_provider is not None:
                os.environ["DATABASE_PROVIDER"] = orig_provider
            else:
                os.environ.pop("DATABASE_PROVIDER", None)

        self.TESTING = True
        self.DEBUG = False
        self.DATABASE_PROVIDER = "sqlite"
        self.DATABASE_PATH = os.environ.get("TEST_DATABASE_PATH", "/tmp/civiclens_test.db")
        self.DATABASE_URL = f"sqlite:///{self.DATABASE_PATH}"
        self.LOG_LEVEL = "WARNING"
        self.NOMINATIM_RATE_LIMIT_SECONDS = 0.0  # Do not throttle in automated unit tests


class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    
    def __init__(self):
        super().__init__()
        if _bool_from_env("FLASK_DEBUG", False):
            raise ConfigurationError("FLASK_DEBUG cannot be enabled in production environment.")
        if not self.SECRET_KEY or self.SECRET_KEY.startswith("insecure-dev-key") or len(self.SECRET_KEY) < 32:
            raise ConfigurationError(
                "In production, SECRET_KEY must be explicitly set to a secure, random string (min 32 characters)."
            )


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name: Optional[str] = None) -> Config:
    """Return an active configuration instance based on environment name."""
    name = (
        env_name or
        os.environ.get("APP_ENV") or
        os.environ.get("FLASK_ENV") or
        os.environ.get("ENVIRONMENT") or
        "development"
    ).lower().strip()
    config_cls = CONFIG_MAP.get(name, DevelopmentConfig)
    return config_cls()
