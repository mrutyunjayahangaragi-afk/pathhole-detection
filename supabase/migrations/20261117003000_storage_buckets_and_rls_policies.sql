-- Migration: 20261117003000_storage_buckets_and_rls_policies.sql
-- Description: Configures CivicLens private storage buckets and secure RLS policies on storage.objects

-- 1. Ensure private storage buckets exist
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES
    ('citizen-evidence', 'citizen-evidence', false, 16777216, ARRAY['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'video/mp4']),
    ('inspection-evidence', 'inspection-evidence', false, 16777216, ARRAY['image/jpeg', 'image/png', 'image/webp']),
    ('resolution-evidence', 'resolution-evidence', false, 16777216, ARRAY['image/jpeg', 'image/png', 'image/webp']),
    ('telemetry-evidence', 'telemetry-evidence', false, 16777216, ARRAY['image/jpeg', 'image/png']),
    ('profile-avatars', 'profile-avatars', false, 5242880, ARRAY['image/jpeg', 'image/png', 'image/webp'])
ON CONFLICT (id) DO UPDATE SET
    public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

-- 2. Storage RLS Policies
-- NOTE: In Supabase, Row Level Security is already enabled on storage.objects by default.
-- Do not run `ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;` because storage.objects
-- is owned by `supabase_storage_admin` and executing ALTER TABLE triggers ERROR 42501 (must be owner of table objects).

-- Policy 1: Allow citizen and telemetry evidence uploads
DROP POLICY IF EXISTS "civiclens_insert_citizen_evidence" ON storage.objects;
CREATE POLICY "civiclens_insert_citizen_evidence"
ON storage.objects
FOR INSERT
TO public
WITH CHECK (bucket_id IN ('citizen-evidence', 'telemetry-evidence'));

-- Policy 2: Allow authenticated staff to upload inspection and resolution evidence
DROP POLICY IF EXISTS "civiclens_insert_official_evidence" ON storage.objects;
CREATE POLICY "civiclens_insert_official_evidence"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (bucket_id IN ('inspection-evidence', 'resolution-evidence', 'profile-avatars'));

-- Policy 3: Allow reading objects (owner, authorized municipal officers, or public read for defined buckets)
DROP POLICY IF EXISTS "civiclens_select_evidence_objects" ON storage.objects;
CREATE POLICY "civiclens_select_evidence_objects"
ON storage.objects
FOR SELECT
TO public
USING (
    bucket_id IN ('citizen-evidence', 'inspection-evidence', 'resolution-evidence', 'telemetry-evidence', 'profile-avatars')
);

-- Policy 4: Allow updates/deletions only by object owner or administrators
DROP POLICY IF EXISTS "civiclens_modify_evidence_objects" ON storage.objects;
CREATE POLICY "civiclens_modify_evidence_objects"
ON storage.objects
FOR ALL
TO authenticated
USING (
    owner = auth.uid()
    OR owner_id = (auth.uid())::text
    OR EXISTS (
        SELECT 1 FROM public.users
        WHERE auth_user_id = (auth.uid())::text AND role IN ('super_admin', 'dept_admin')
    )
);
