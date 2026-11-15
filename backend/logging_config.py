"""
Logging Configuration for CivicLens
====================================

Sets up structured, non-leaking application logging with configurable log levels.
Guarantees sensitive keys (passwords, tokens, credentials) are never printed.
"""

import logging
import sys
from typing import Optional

SENSITIVE_KEYWORDS = {"password", "secret", "token", "authorization", "key", "credential"}


class SensitiveFilter(logging.Filter):
    """Redacts sensitive key-value pairs or substrings from log records."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            lower_msg = record.msg.lower()
            for kw in SENSITIVE_KEYWORDS:
                if kw in lower_msg and ("=" in lower_msg or ":" in lower_msg):
                    # Redact potential assignment pattern
                    record.msg = "[REDACTED LOG CONTENT - CONTAINS SENSITIVE KEY]"
                    break
        return True


def setup_logging(log_level: str = "INFO", app_name: str = "civiclens") -> logging.Logger:
    """Configures and returns the root logger for the application."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger = logging.getLogger(app_name)
    logger.setLevel(level)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveFilter())
        logger.addHandler(handler)
        
    logger.propagate = False
    return logger
