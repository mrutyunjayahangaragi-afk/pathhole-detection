# ==============================================================================
# CivicLens Production Containerfile
# AI-Powered Multilingual Civic Grievance & Infrastructure Triage System
# Based on Roadstate by halo-112 (MIT License)
# ==============================================================================

# --- Stage 1: Build & Dependencies ---
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /install

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --prefix=/install/deps -r requirements.txt


# --- Stage 2: Final Runtime ---
FROM python:3.13-slim-bookworm AS runner

LABEL org.opencontainers.image.title="CivicLens" \
      org.opencontainers.image.description="AI-Powered Multilingual Civic Grievance & Infrastructure Triage System" \
      org.opencontainers.image.vendor="CivicLens Municipal Team" \
      org.opencontainers.image.authors="halo-112, CivicLens Contributors" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5055 \
    HOST=0.0.0.0 \
    PATH="/app/deps/bin:$PATH" \
    PYTHONPATH="/app/deps/lib/python3.13/site-packages:$PYTHONPATH"

# Install minimal runtime dependencies (curl for healthchecks, libpq for PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 10001 civiclens && \
    useradd -u 10001 -g civiclens -s /bin/bash -m civiclens

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /install/deps /app/deps

# Copy application source code
COPY --chown=civiclens:civiclens backend /app/backend
COPY --chown=civiclens:civiclens frontend /app/frontend
COPY --chown=civiclens:civiclens dashboard /app/dashboard
COPY --chown=civiclens:civiclens gunicorn.conf.py /app/gunicorn.conf.py
COPY --chown=civiclens:civiclens alembic.ini /app/alembic.ini

# Create directories for runtime SQLite and uploads if needed
RUN mkdir -p /app/data /app/uploads && \
    chown -R civiclens:civiclens /app

USER civiclens:civiclens

EXPOSE 5055

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:5055/api/health || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py", "backend.app:create_app()"]
