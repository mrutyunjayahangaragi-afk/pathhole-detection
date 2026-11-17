-- Migration: 20261117160000_create_homepage_showcase_items.sql
-- Description: Creates homepage_showcase_items table for the CivicLens Impact Showcase

CREATE TABLE IF NOT EXISTS homepage_showcase_items (
    id VARCHAR(36) PRIMARY KEY,
    evidence_asset_id VARCHAR(36) REFERENCES evidence_assets_v2(id) ON DELETE SET NULL,
    incident_id VARCHAR(36) REFERENCES incidents_v2(id) ON DELETE SET NULL,
    uploader_id VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    uploader_role_snapshot VARCHAR(50) NOT NULL DEFAULT 'municipal_officer',
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(50) NOT NULL DEFAULT 'pothole',
    media_type VARCHAR(20) NOT NULL DEFAULT 'IMAGE',  -- 'IMAGE' or 'VIDEO'
    storage_bucket VARCHAR(100) NOT NULL DEFAULT 'inspection-evidence',
    storage_object_path TEXT NOT NULL,
    thumbnail_object_path TEXT,
    public_location_label VARCHAR(255) NOT NULL,
    content_hash VARCHAR(64),
    publication_status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',   -- DRAFT, PENDING_REVIEW, APPROVED, PUBLISHED, UNPUBLISHED, ARCHIVED
    moderation_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED
    before_after_type VARCHAR(20) NOT NULL DEFAULT 'STANDALONE', -- 'BEFORE', 'AFTER', 'STANDALONE'
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_featured BOOLEAN NOT NULL DEFAULT FALSE,
    starts_at TIMESTAMP WITH TIME ZONE,
    ends_at TIMESTAMP WITH TIME ZONE,
    approved_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,
    approved_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_showcase_pub_status ON homepage_showcase_items(publication_status, moderation_status);
CREATE INDEX IF NOT EXISTS ix_showcase_sort_order ON homepage_showcase_items(sort_order);
CREATE INDEX IF NOT EXISTS ix_showcase_category ON homepage_showcase_items(category);
CREATE INDEX IF NOT EXISTS ix_showcase_incident ON homepage_showcase_items(incident_id);
