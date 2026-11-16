-- =============================================================================
-- Migration: 20261116210005_create_audit_logs.sql
-- Description: Audit logging for municipal workflows and authorization changes
-- =============================================================================

CREATE TABLE IF NOT EXISTS audit_logs_v2 (
    id VARCHAR(36) NOT NULL,
    actor_id VARCHAR(36),
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(36) NOT NULL,
    municipality_id VARCHAR(36),
    department_id VARCHAR(36),
    previous_state TEXT,
    new_state TEXT,
    details TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    FOREIGN KEY (actor_id) REFERENCES users (id) ON DELETE SET NULL,
    FOREIGN KEY (municipality_id) REFERENCES municipalities (id) ON DELETE SET NULL,
    FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_v2_entity ON audit_logs_v2 (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_v2_actor ON audit_logs_v2 (actor_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_v2_created ON audit_logs_v2 (created_at);
