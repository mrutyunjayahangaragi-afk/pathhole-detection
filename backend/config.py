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
        self.ENV = os.environ.get("FLASK_ENV", "development").lower()
        self.DEBUG = _bool_from_env("FLASK_DEBUG", False)
        self.TESTING = False
        
        self.HOST = os.environ.get("HOST", "0.0.0.0")
        try:
            self.PORT = int(os.environ.get("PORT", "5000"))
            if not (1 <= self.PORT <= 65535):
                raise ConfigurationError(f"PORT must be between 1 and 65535, got {self.PORT}")
        except ValueError as e:
            raise ConfigurationError(f"Invalid PORT value: {e}") from e

        self.SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-dev-key-civiclens-change-in-production")
        
        # Database
        self.RAW_DB_PATH = os.environ.get("DATABASE_PATH", "backend/pothole_reports.db")
        self.DATABASE_PATH = _resolve_db_path(self.RAW_DB_PATH)
        self.DATABASE_URL = os.environ.get("DATABASE_URL")  # Future PostgreSQL URL
        
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
        self.CORS_ORIGINS: List[str] = [
            o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()
        ]

        # Logging
        self.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

        # Uploads
        self.UPLOAD_FOLDER = str(PROJECT_ROOT / os.environ.get("UPLOAD_FOLDER", "uploads"))
        self.MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "16")) * 1024 * 1024


class DevelopmentConfig(Config):
    """Development environment configuration."""
    def __init__(self):
        super().__init__()
        self.DEBUG = True


class TestingConfig(Config):
    """Testing environment configuration."""
    __test__ = False  # Prevent pytest from treating this configuration as a test suite
    def __init__(self):
        super().__init__()
        self.TESTING = True
        self.DEBUG = False
        self.DATABASE_PATH = os.environ.get("TEST_DATABASE_PATH", "/tmp/civiclens_test.db")
        self.LOG_LEVEL = "WARNING"
        self.NOMINATIM_RATE_LIMIT_SECONDS = 0.0  # Do not throttle in automated unit tests


class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    
    def __init__(self):
        super().__init__()
        if self.SECRET_KEY.startswith("insecure-dev-key"):
            raise ConfigurationError(
                "In production, SECRET_KEY must be explicitly set to a secure secret."
            )


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env_name: Optional[str] = None) -> Config:
    """Return an active configuration instance based on environment name."""
    name = (env_name or os.environ.get("FLASK_ENV", "development")).lower()
    config_cls = CONFIG_MAP.get(name, DevelopmentConfig)
    return config_cls()
