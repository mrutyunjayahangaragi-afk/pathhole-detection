-- =============================================================================
-- CivicLens Seed Data (Reference Entities Only)
-- =============================================================================
-- Idempotent initialization of default municipal bodies and departments.
-- Does not insert synthetic users, fake reports, or mock telemetry.
-- =============================================================================

INSERT INTO municipalities (id, name, code, state, status, created_at, updated_at)
VALUES ('9951f5f4-8ada-4604-b714-054794edeccd', 'Bruhat Bengaluru Mahanagara Palike', 'BBMP', 'Karnataka', 'active', NOW(), NOW())
ON CONFLICT (name) DO NOTHING;

INSERT INTO departments (id, municipality_id, name, code, description, contact_email, is_active, created_at, updated_at)
VALUES 
    ('d6bf33be-c40d-490c-8de8-e0ef0c720dff', '9951f5f4-8ada-4604-b714-054794edeccd', 'Road & Highway Maintenance', 'ROAD_MAINT', 'Responsible for asphalt, potholes, road resurfacing, and pavement repairs.', 'roads@civiclens.gov.in', true, NOW(), NOW()),
    ('71a9386c-48c6-43b9-a417-ccca27233767', '9951f5f4-8ada-4604-b714-054794edeccd', 'Traffic Engineering & Signals', 'TRAFFIC_ENG', 'Responsible for road signs, traffic signals, road markings, and speed bumps.', 'traffic@civiclens.gov.in', true, NOW(), NOW()),
    ('e2f6942c-29b6-455b-bb3b-f4581f4a4342', '9951f5f4-8ada-4604-b714-054794edeccd', 'Stormwater & Drainage Division', 'DRAINAGE', 'Responsible for open drains, storm culverts, waterlogging, and manhole lids.', 'drainage@civiclens.gov.in', true, NOW(), NOW()),
    ('b9d8856e-8ee5-4b0d-b873-ea1ea1994119', '9951f5f4-8ada-4604-b714-054794edeccd', 'Street Lighting & Electrical Works', 'LIGHTING', 'Responsible for street lamps, high masts, exposed electrical wiring, and poles.', 'lighting@civiclens.gov.in', true, NOW(), NOW()),
    ('683fa272-3ef4-4348-912f-6821262d1c68', '9951f5f4-8ada-4604-b714-054794edeccd', 'Solid Waste Management', 'SOLID_WASTE', 'Responsible for garbage mounds, debris dumping, sweepers, and bins.', 'waste@civiclens.gov.in', true, NOW(), NOW()),
    ('c4224ad8-2947-4927-a068-075b9f935327', '9951f5f4-8ada-4604-b714-054794edeccd', 'Pedestrian Walkways & Footpaths', 'FOOTPATHS', 'Responsible for pedestrian sidewalks, paving tiles, bollards, and tactile paving.', 'footpaths@civiclens.gov.in', true, NOW(), NOW())
ON CONFLICT (code) DO NOTHING;
