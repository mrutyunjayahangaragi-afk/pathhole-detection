-- =============================================================================
-- CivicLens: Supabase PostgreSQL Row Level Security (RLS) & Access Control
-- =============================================================================
-- Run in Supabase SQL Editor to enforce database-level access controls.
-- Complements Flask backend middleware by providing defense-in-depth isolation.
-- =============================================================================

-- Enable Row Level Security on core application tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE citizen_reports_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE municipalities ENABLE ROW LEVEL SECURITY;
ALTER TABLE official_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE telemetry_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE telemetry_events ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- 1. Public Incidents Policies
-- -----------------------------------------------------------------------------
-- Public users (and unauthenticated visitors) can read verified, non-rejected incidents
CREATE POLICY "Public can view verified canonical incidents"
    ON incidents_v2
    FOR SELECT
    USING (status NOT IN ('rejected', 'closed_unverified'));

-- -----------------------------------------------------------------------------
-- 2. Citizen Reports Policies
-- -----------------------------------------------------------------------------
-- Citizens can view their own reports
CREATE POLICY "Citizens can view own reports"
    ON citizen_reports_v2
    FOR SELECT
    USING (auth.uid()::text = citizen_id);

-- Citizens can insert their own reports
CREATE POLICY "Citizens can insert own reports"
    ON citizen_reports_v2
    FOR INSERT
    WITH CHECK (auth.uid()::text = citizen_id);

-- -----------------------------------------------------------------------------
-- 3. Municipal Personnel Policies
-- -----------------------------------------------------------------------------
-- Municipal personnel can view all incidents and reports
CREATE POLICY "Officials can view all incidents"
    ON incidents_v2
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM users
            WHERE users.id = auth.uid()::text
            AND users.role IN ('municipal_officer', 'dept_admin', 'municipal_admin', 'system_admin')
        )
    );

-- Municipal personnel can update incidents
CREATE POLICY "Officials can update assigned incidents"
    ON incidents_v2
    FOR UPDATE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM users
            WHERE users.id = auth.uid()::text
            AND users.role IN ('municipal_officer', 'dept_admin', 'municipal_admin', 'system_admin')
        )
    );

-- -----------------------------------------------------------------------------
-- 4. Official Invitations Policies
-- -----------------------------------------------------------------------------
-- Only administrators can read or create official invitations
CREATE POLICY "Admins can view invitations"
    ON official_invitations
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM users
            WHERE users.id = auth.uid()::text
            AND users.role IN ('dept_admin', 'municipal_admin', 'system_admin')
        )
    );

CREATE POLICY "Admins can create invitations"
    ON official_invitations
    FOR INSERT
    TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM users
            WHERE users.id = auth.uid()::text
            AND users.role IN ('dept_admin', 'municipal_admin', 'system_admin')
        )
    );

-- -----------------------------------------------------------------------------
-- 5. Service Role Bypass
-- -----------------------------------------------------------------------------
-- Backend server connection using service_role key has unrestricted administrative access
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO service_role;
