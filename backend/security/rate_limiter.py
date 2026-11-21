"""
CivicLens Rate Limiting
======================
Provides Flask-Limiter integration for protecting auth endpoints.
Includes a graceful fallback if Flask-Limiter is missing so the application
never fails to start.
"""

import logging

logger = logging.getLogger("civiclens.security.rate_limiter")

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[],
        storage_uri="memory://",
        strategy="fixed-window"
    )
except ImportError:
    logger.warning("Flask-Limiter is not installed. Falling back to no-op rate limiter.")

    class _NoOpLimiter:
        """Fallback no-op limiter when flask-limiter is not installed."""
        def init_app(self, app):
            pass

        def limit(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator

    limiter = _NoOpLimiter()
