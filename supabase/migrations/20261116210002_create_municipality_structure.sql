-- =============================================================================
-- Migration: 20261116210002_create_municipality_structure.sql
-- Description: Create municipality and municipal department hierarchies
-- =============================================================================

CREATE TABLE IF NOT EXISTS municipalities (
    id VARCHAR(36) NOT NULL,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    state VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_municipality_status CHECK (status IN ('active', 'inactive', 'suspended')),
    UNIQUE (name)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_municipalities_code ON municipalities (code);

CREATE TABLE IF NOT EXISTS departments (
    id VARCHAR(36) NOT NULL,
    municipality_id VARCHAR(36) REFERENCES municipalities(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    description TEXT,
    contact_email VARCHAR(320),
    contact_phone VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    FOREIGN KEY (municipality_id) REFERENCES municipalities (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_departments_code ON departments (code);
CREATE INDEX IF NOT EXISTS ix_departments_municipality ON departments (municipality_id);
