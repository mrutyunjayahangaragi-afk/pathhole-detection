-- =============================================================================
-- Migration: 20261117190000_official_invitations_rls.sql
-- Description: Row Level Security for official_invitations table
-- =============================================================================

ALTER TABLE official_invitations ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'official_invitations' 
        AND policyname = 'authenticated_staff_read_invitations'
    ) THEN
        CREATE POLICY "authenticated_staff_read_invitations"
          ON official_invitations
          FOR SELECT
          USING (auth.role() = 'authenticated');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'official_invitations' 
        AND policyname = 'service_role_manage_invitations'
    ) THEN
        CREATE POLICY "service_role_manage_invitations"
          ON official_invitations
          FOR ALL
          USING (auth.role() = 'service_role')
          WITH CHECK (auth.role() = 'service_role');
    END IF;
END $$;
