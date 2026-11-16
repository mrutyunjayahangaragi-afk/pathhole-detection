"""
CivicLens Production Gunicorn WSGI Configuration
================================================
Configures high-concurrency, low-latency WSGI execution for CivicLens
under Linux/macOS container and cloud VM environments.
"""

import os
import multiprocessing

# Network Binding
bind = f"{os.getenv('HOST', '0.0.0.0')}:{os.getenv('PORT', '5055')}"
backlog = 2048

# Worker Processes & Concurrency
# Formula: (2 x cores) + 1, capped appropriately for container memory constraints
cpu_count = multiprocessing.cpu_count()
workers = int(os.getenv("WEB_CONCURRENCY", min(max(2, cpu_count * 2 + 1), 8)))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")
threads = int(os.getenv("GUNICORN_THREADS", "2"))

# Worker Lifecycle & Recycling (prevents memory leaks)
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "100"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))

# Process Naming
proc_name = "civiclens_wsgi"

# Structured Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)ss'


def on_starting(server):
    """Invoked just before the master process is initialized."""
    server.log.info("Starting CivicLens WSGI server on %s with %d workers (threads=%d)...", bind, workers, threads)


def on_exit(server):
    """Invoked just before exiting Gunicorn."""
    server.log.info("CivicLens WSGI server stopped.")
