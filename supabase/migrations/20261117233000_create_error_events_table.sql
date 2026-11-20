-- Migration: Create application_error_events table for centralized exception tracking
-- Generated: 2026-11-17 23:30:00

CREATE TABLE IF NOT EXISTS application_error_events (
    id VARCHAR(36) PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    endpoint VARCHAR(255),
    method VARCHAR(16),
    user_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    error_code VARCHAR(64),
    error_type VARCHAR(128) NOT NULL,
    error_message TEXT NOT NULL,
    traceback TEXT,
    sanitized_request_params JSONB,
    client_ip VARCHAR(64),
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_error_events_timestamp ON application_error_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_error_events_error_code ON application_error_events(error_code);
CREATE INDEX IF NOT EXISTS idx_error_events_user_id ON application_error_events(user_id);
