-- =============================================================================
-- Migration: 20261116210006_create_map_public_views_and_indexes.sql
-- Description: Composite query performance indexes and public transparency views
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_incidents_v2_coords ON incidents_v2 (latitude, longitude);
CREATE INDEX IF NOT EXISTS ix_incidents_v2_status ON incidents_v2 (status);
CREATE INDEX IF NOT EXISTS ix_incidents_v2_category ON incidents_v2 (category);
CREATE INDEX IF NOT EXISTS ix_incidents_v2_dept ON incidents_v2 (department_id);
CREATE INDEX IF NOT EXISTS ix_incidents_status_cat ON incidents_v2(status, category);
CREATE INDEX IF NOT EXISTS ix_incidents_sev_pri ON incidents_v2(severity, priority);

CREATE INDEX IF NOT EXISTS ix_reports_v2_coords ON citizen_reports_v2 (latitude, longitude);
CREATE INDEX IF NOT EXISTS ix_reports_v2_citizen ON citizen_reports_v2 (citizen_id);
CREATE INDEX IF NOT EXISTS ix_reports_v2_status ON citizen_reports_v2 (status);
CREATE INDEX IF NOT EXISTS ix_reports_cit_created ON citizen_reports_v2(citizen_id, created_at);

-- Public view for safe transparent incident map exploration without citizen PII
CREATE OR REPLACE VIEW public_incidents_view AS
SELECT 
    i.id,
    i.incident_reference,
    i.title,
    i.description,
    i.category,
    i.status,
    i.severity,
    i.priority,
    i.latitude,
    i.longitude,
    i.address,
    i.report_count,
    i.verification_confidence,
    i.department_id,
    d.name AS department_name,
    i.created_at,
    i.updated_at,
    i.resolved_at
FROM incidents_v2 i
LEFT JOIN departments d ON i.department_id = d.id
WHERE i.status NOT IN ('rejected', 'closed_unverified');
