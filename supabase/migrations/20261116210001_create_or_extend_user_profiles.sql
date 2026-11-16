-- =============================================================================
-- Migration: 20261116210001_create_or_extend_user_profiles.sql
-- Description: Create or extend user profiles linked to Supabase Auth
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) NOT NULL,
    auth_user_id VARCHAR(64),
    display_name VARCHAR(255) NOT NULL,
    email VARCHAR(320),
    phone VARCHAR(20),
    role VARCHAR(30) NOT NULL DEFAULT 'citizen',
    preferred_language VARCHAR(5) NOT NULL DEFAULT 'en',
    password_hash VARCHAR(255),
    last_login_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT ck_users_role CHECK (role IN ('citizen', 'municipal_officer', 'dept_admin', 'municipal_admin', 'system_admin')),
    UNIQUE (email)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'auth_user_id'
    ) THEN
        ALTER TABLE users ADD COLUMN auth_user_id VARCHAR(64);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_auth_user_id ON users (auth_user_id) WHERE auth_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE INDEX IF NOT EXISTS ix_users_role ON users (role);
