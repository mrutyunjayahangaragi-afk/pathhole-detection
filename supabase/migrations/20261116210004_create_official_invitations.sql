-- =============================================================================
-- Migration: 20261116210004_create_official_invitations.sql
-- Description: Invitation-based onboarding for municipal officials
-- =============================================================================

CREATE TABLE IF NOT EXISTS official_invitations (
    id VARCHAR(36) NOT NULL,
    invited_email VARCHAR(320) NOT NULL,
    intended_role VARCHAR(30) NOT NULL,
    municipality_id VARCHAR(36) NOT NULL,
    department_id VARCHAR(36),
    token_hash VARCHAR(64) NOT NULL,
    invited_by VARCHAR(36) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    accepted_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_invitation_status CHECK (status IN ('pending', 'accepted', 'expired', 'revoked')),
    CONSTRAINT ck_invitation_role CHECK (intended_role IN ('municipal_officer', 'dept_admin', 'municipal_admin', 'system_admin')),
    FOREIGN KEY (municipality_id) REFERENCES municipalities (id) ON DELETE CASCADE,
    FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL,
    FOREIGN KEY (invited_by) REFERENCES users (id) ON DELETE CASCADE,
    UNIQUE (token_hash)
);

CREATE INDEX IF NOT EXISTS ix_invitations_email ON official_invitations (invited_email);
CREATE INDEX IF NOT EXISTS ix_invitations_status ON official_invitations (status);
CREATE UNIQUE INDEX IF NOT EXISTS ix_invitations_token_hash ON official_invitations (token_hash);
