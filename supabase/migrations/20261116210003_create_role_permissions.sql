-- =============================================================================
-- Migration: 20261116210003_create_role_permissions.sql
-- Description: Department memberships, officer assignments, and role permissions
-- =============================================================================

CREATE TABLE IF NOT EXISTS department_memberships (
    id VARCHAR(36) NOT NULL,
    department_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    official_role VARCHAR(30) NOT NULL,
    assigned_by VARCHAR(36),
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_dept_official_role CHECK (official_role IN ('municipal_officer', 'dept_admin', 'municipal_admin', 'system_admin')),
    FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (assigned_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_dept_memberships_dept ON department_memberships (department_id);
CREATE INDEX IF NOT EXISTS ix_dept_memberships_user ON department_memberships (user_id);
