-- =============================================================================
-- Migration: 20261117213000_add_data_provenance_columns.sql
-- Description: Adds provenance tracking to identify data origin
-- =============================================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS provenance VARCHAR(32) DEFAULT 'REAL_USER_DATA';
ALTER TABLE incidents_v2 ADD COLUMN IF NOT EXISTS provenance VARCHAR(32) DEFAULT 'REAL_USER_DATA';
ALTER TABLE citizen_reports_v2 ADD COLUMN IF NOT EXISTS provenance VARCHAR(32) DEFAULT 'REAL_USER_DATA';
ALTER TABLE departments ADD COLUMN IF NOT EXISTS provenance VARCHAR(32) DEFAULT 'APPROVED_SEED_DATA';

-- Indexes for efficient provenance filtering
CREATE INDEX IF NOT EXISTS ix_users_provenance ON users (provenance);
CREATE INDEX IF NOT EXISTS ix_incidents_provenance ON incidents_v2 (provenance);
CREATE INDEX IF NOT EXISTS ix_citizen_reports_provenance ON citizen_reports_v2 (provenance);
