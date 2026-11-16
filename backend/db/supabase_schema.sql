-- =============================================================================
-- CivicLens: Complete Supabase PostgreSQL Schema & RLS Setup
-- =============================================================================
-- Run this entire script in Supabase SQL Editor to set up tables, indexes, and RLS.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Table: audit_logs_v2
CREATE TABLE IF NOT EXISTS audit_logs_v2 (
	id VARCHAR(36) NOT NULL, 
	actor_id VARCHAR(36), 
	action VARCHAR(50) NOT NULL, 
	entity_type VARCHAR(50) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	details TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

-- Table: evidence_assets_v2
CREATE TABLE IF NOT EXISTS evidence_assets_v2 (
	id VARCHAR(36) NOT NULL, 
	content_sha256 VARCHAR(64), 
	perceptual_hash VARCHAR(64), 
	hash_algorithm VARCHAR(30), 
	hash_version VARCHAR(20), 
	storage_key TEXT, 
	media_type VARCHAR(50), 
	file_size_bytes INTEGER, 
	original_filename VARCHAR(255), 
	captured_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (content_sha256)
);

-- Table: municipalities
CREATE TABLE IF NOT EXISTS municipalities (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	code VARCHAR(50) NOT NULL, 
	state VARCHAR(100) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_municipality_status CHECK (status IN ('active','inactive','suspended')), 
	UNIQUE (name)
);

-- Table: notification_events
CREATE TABLE IF NOT EXISTS notification_events (
	id VARCHAR(36) NOT NULL, 
	event_type VARCHAR(50) NOT NULL, 
	event_payload TEXT NOT NULL, 
	idempotency_key VARCHAR(100) NOT NULL, 
	processing_status VARCHAR(30) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	processed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_notif_event_status CHECK (processing_status IN ('PENDING','PROCESSING','COMPLETED','FAILED')), 
	UNIQUE (idempotency_key)
);

-- Table: telemetry_devices
CREATE TABLE IF NOT EXISTS telemetry_devices (
	id VARCHAR(36) NOT NULL, 
	device_id VARCHAR(50) NOT NULL, 
	device_name VARCHAR(100) NOT NULL, 
	device_type VARCHAR(30) NOT NULL, 
	assigned_vehicle VARCHAR(50), 
	api_key_hash VARCHAR(128) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	camera_stream_url VARCHAR(255), 
	camera_status VARCHAR(30) NOT NULL, 
	last_heartbeat_at TIMESTAMP WITH TIME ZONE, 
	last_latitude FLOAT, 
	last_longitude FLOAT, 
	total_events_ingested INTEGER NOT NULL, 
	firmware_version VARCHAR(30), 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_telemetry_device_status CHECK (status IN ('CONNECTED','STALE','DISCONNECTED','NOT_CONFIGURED','ERROR')), 
	CONSTRAINT ck_telemetry_camera_status CHECK (camera_status IN ('not_configured','offline','active','error')), 
	UNIQUE (device_id)
);

-- Table: users
CREATE TABLE IF NOT EXISTS users (
	id VARCHAR(36) NOT NULL, 
	display_name VARCHAR(255) NOT NULL, 
	email VARCHAR(320), 
	phone VARCHAR(20), 
	role VARCHAR(30) NOT NULL, 
	preferred_language VARCHAR(5) NOT NULL, 
	password_hash VARCHAR(255), 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_users_role CHECK (role IN ('citizen','municipal_officer','dept_admin','municipal_admin','system_admin')), 
	UNIQUE (email)
);

-- Table: citizen_reports_v2
CREATE TABLE IF NOT EXISTS citizen_reports_v2 (
	id VARCHAR(36) NOT NULL, 
	citizen_id VARCHAR(36), 
	report_reference VARCHAR(20), 
	title VARCHAR(255), 
	description TEXT, 
	reported_severity VARCHAR(20), 
	idempotency_key VARCHAR(64), 
	is_manual_location BOOLEAN NOT NULL, 
	latitude FLOAT NOT NULL, 
	longitude FLOAT NOT NULL, 
	location_accuracy_m FLOAT, 
	address TEXT, 
	original_language VARCHAR(5) NOT NULL, 
	translated_description TEXT, 
	detected_language VARCHAR(10), 
	language_detection_confidence FLOAT, 
	language_detection_model VARCHAR(50), 
	language_detection_status VARCHAR(30) NOT NULL, 
	submission_channel VARCHAR(30) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	submitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_report_channel CHECK (submission_channel IN ('mobile_app','web','vehicle_telematics','manual_official','phone_call')), 
	CONSTRAINT ck_report_status CHECK (status IN ('submitted','under_review','linked','rejected','withdrawn','acknowledged','resolved')), 
	CONSTRAINT ck_report_severity CHECK (reported_severity IS NULL OR reported_severity IN ('minor','moderate','severe','critical')), 
	FOREIGN KEY(citizen_id) REFERENCES users (id) ON DELETE SET NULL, 
	UNIQUE (report_reference)
);

-- Table: departments
CREATE TABLE IF NOT EXISTS departments (
	id VARCHAR(36) NOT NULL, 
	municipality_id VARCHAR(36), 
	name VARCHAR(255) NOT NULL, 
	code VARCHAR(50), 
	description TEXT, 
	contact_email VARCHAR(320), 
	contact_phone VARCHAR(20), 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(municipality_id) REFERENCES municipalities (id) ON DELETE SET NULL, 
	UNIQUE (name)
);

-- Table: detection_runs
CREATE TABLE IF NOT EXISTS detection_runs (
	id VARCHAR(36) NOT NULL, 
	evidence_asset_id VARCHAR(36) NOT NULL, 
	model_name VARCHAR(100) NOT NULL, 
	model_version VARCHAR(50) NOT NULL, 
	processing_status VARCHAR(20) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	processing_duration_ms FLOAT, 
	error_code VARCHAR(50), 
	error_message TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_detection_run_status CHECK (processing_status IN ('pending','processing','running','completed','failed','needs_review')), 
	FOREIGN KEY(evidence_asset_id) REFERENCES evidence_assets_v2 (id) ON DELETE CASCADE
);

-- Table: notification_deliveries
CREATE TABLE IF NOT EXISTS notification_deliveries (
	id VARCHAR(36) NOT NULL, 
	event_id VARCHAR(36) NOT NULL, 
	recipient_id VARCHAR(36) NOT NULL, 
	channel VARCHAR(20) NOT NULL, 
	provider VARCHAR(50) NOT NULL, 
	provider_reference VARCHAR(100), 
	delivery_status VARCHAR(30) NOT NULL, 
	attempts INTEGER NOT NULL, 
	next_retry_at TIMESTAMP WITH TIME ZONE, 
	last_error_code VARCHAR(50), 
	last_error_message TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_delivery_channel CHECK (channel IN ('in_app','email','sms','whatsapp','push')), 
	CONSTRAINT ck_delivery_status CHECK (delivery_status IN ('CREATED','QUEUED','PROCESSING','PROVIDER_ACCEPTED','DELIVERED','FAILED','BLOCKED','CANCELLED')), 
	FOREIGN KEY(event_id) REFERENCES notification_events (id) ON DELETE CASCADE, 
	FOREIGN KEY(recipient_id) REFERENCES users (id) ON DELETE CASCADE
);

-- Table: notification_preferences
CREATE TABLE IF NOT EXISTS notification_preferences (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	in_app_enabled BOOLEAN NOT NULL, 
	email_enabled BOOLEAN NOT NULL, 
	sms_enabled BOOLEAN NOT NULL, 
	whatsapp_enabled BOOLEAN NOT NULL, 
	push_enabled BOOLEAN NOT NULL, 
	quiet_hours_enabled BOOLEAN NOT NULL, 
	quiet_hours_start VARCHAR(5), 
	quiet_hours_end VARCHAR(5), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- Table: telemetry_events
CREATE TABLE IF NOT EXISTS telemetry_events (
	id VARCHAR(36) NOT NULL, 
	event_id VARCHAR(64) NOT NULL, 
	device_id VARCHAR(36) NOT NULL, 
	latitude FLOAT NOT NULL, 
	longitude FLOAT NOT NULL, 
	severity VARCHAR(15) NOT NULL, 
	est_depth_cm FLOAT, 
	confidence FLOAT NOT NULL, 
	vehicle_speed_kmh FLOAT, 
	image_ref TEXT, 
	road_surface VARCHAR(50), 
	raw_payload JSON, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	ingested_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_telem_event_severity CHECK (severity IN ('minor','moderate','severe','critical')), 
	UNIQUE (event_id), 
	FOREIGN KEY(device_id) REFERENCES telemetry_devices (id) ON DELETE CASCADE
);

-- Table: user_notifications
CREATE TABLE IF NOT EXISTS user_notifications (
	id VARCHAR(36) NOT NULL, 
	recipient_id VARCHAR(36) NOT NULL, 
	event_id VARCHAR(36), 
	category VARCHAR(30) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	message TEXT NOT NULL, 
	language VARCHAR(5) NOT NULL, 
	related_report_id VARCHAR(36), 
	related_incident_id VARCHAR(36), 
	is_read BOOLEAN NOT NULL, 
	read_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(recipient_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(event_id) REFERENCES notification_events (id) ON DELETE SET NULL
);

-- Table: web_push_subscriptions
CREATE TABLE IF NOT EXISTS web_push_subscriptions (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	endpoint TEXT NOT NULL, 
	p256dh VARCHAR(255) NOT NULL, 
	auth VARCHAR(255) NOT NULL, 
	user_agent VARCHAR(255), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_push_endpoint UNIQUE (user_id, endpoint), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- Table: department_memberships
CREATE TABLE IF NOT EXISTS department_memberships (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	department_id VARCHAR(36) NOT NULL, 
	role_in_dept VARCHAR(30) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	joined_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_dept_member_role CHECK (role_in_dept IN ('officer','lead','admin')), 
	CONSTRAINT uq_user_dept UNIQUE (user_id, department_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE CASCADE
);

-- Table: detections_v3
CREATE TABLE IF NOT EXISTS detections_v3 (
	id VARCHAR(36) NOT NULL, 
	detection_run_id VARCHAR(36) NOT NULL, 
	evidence_asset_id VARCHAR(36), 
	detected_category VARCHAR(50) NOT NULL, 
	confidence_score FLOAT NOT NULL, 
	confidence_tier VARCHAR(20), 
	bbox_x INTEGER, 
	bbox_y INTEGER, 
	bbox_w INTEGER, 
	bbox_h INTEGER, 
	normalized_xmin FLOAT, 
	normalized_ymin FLOAT, 
	normalized_xmax FLOAT, 
	normalized_ymax FLOAT, 
	image_width INTEGER, 
	image_height INTEGER, 
	est_depth_cm FLOAT, 
	severity VARCHAR(10), 
	model_version VARCHAR(50), 
	review_status VARCHAR(20) NOT NULL, 
	reviewed_by VARCHAR(36), 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	review_notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_detection_confidence CHECK (confidence_score BETWEEN 0.0 AND 1.0), 
	CONSTRAINT ck_detection_review_status CHECK (review_status IN ('unreviewed','confirmed','rejected','uncertain','corrected')), 
	FOREIGN KEY(detection_run_id) REFERENCES detection_runs (id) ON DELETE CASCADE, 
	FOREIGN KEY(evidence_asset_id) REFERENCES evidence_assets_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL
);

-- Table: incidents_v2
CREATE TABLE IF NOT EXISTS incidents_v2 (
	id VARCHAR(36) NOT NULL, 
	incident_reference VARCHAR(20), 
	category VARCHAR(50) NOT NULL, 
	description TEXT, 
	severity VARCHAR(10) NOT NULL, 
	priority VARCHAR(10) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	department_id VARCHAR(36), 
	assigned_officer_id VARCHAR(36), 
	latitude FLOAT NOT NULL, 
	longitude FLOAT NOT NULL, 
	location_accuracy_m FLOAT, 
	address TEXT, 
	report_count INTEGER NOT NULL, 
	est_depth_cm FLOAT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	reopened_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_incident_severity CHECK (severity IN ('minor','moderate','severe','critical')), 
	CONSTRAINT ck_incident_priority CHECK (priority IN ('low','normal','high','critical')), 
	CONSTRAINT ck_incident_status CHECK (status IN ('new','awaiting_verification','verified','assigned','in_progress','on_hold','resolved','reopened','closed','rejected','reported','acknowledged','scheduled','repaired')), 
	CONSTRAINT ck_incident_category CHECK (category IN ('pothole','road_damage','bridge_damage','garbage','water_leakage','drainage','broken_streetlight','other')), 
	UNIQUE (incident_reference), 
	FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE SET NULL, 
	FOREIGN KEY(assigned_officer_id) REFERENCES users (id) ON DELETE SET NULL
);

-- Table: location_records
CREATE TABLE IF NOT EXISTS location_records (
	id VARCHAR(36) NOT NULL, 
	report_id VARCHAR(36) NOT NULL, 
	latitude FLOAT NOT NULL, 
	longitude FLOAT NOT NULL, 
	location_accuracy_m FLOAT, 
	location_source VARCHAR(30) NOT NULL, 
	road_name VARCHAR(255), 
	road_type VARCHAR(50), 
	locality VARCHAR(255), 
	suburb VARCHAR(255), 
	city VARCHAR(255), 
	district VARCHAR(255), 
	state VARCHAR(255), 
	postal_code VARCHAR(20), 
	country VARCHAR(100), 
	normalized_address TEXT, 
	raw_geocoding_json TEXT, 
	geocoding_provider VARCHAR(50) NOT NULL, 
	geocoding_status VARCHAR(30) NOT NULL, 
	geocoded_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_loc_source CHECK (location_source IN ('device_gps','manual_pin','exif_gps','citizen_text')), 
	UNIQUE (report_id), 
	FOREIGN KEY(report_id) REFERENCES citizen_reports_v2 (id) ON DELETE CASCADE
);

-- Table: official_invitations
CREATE TABLE IF NOT EXISTS official_invitations (
	id VARCHAR(36) NOT NULL, 
	invited_email VARCHAR(320) NOT NULL, 
	intended_role VARCHAR(30) NOT NULL, 
	municipality_id VARCHAR(36), 
	department_id VARCHAR(36), 
	token_hash VARCHAR(128) NOT NULL, 
	invited_by_id VARCHAR(36), 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	accepted_at TIMESTAMP WITH TIME ZONE, 
	revoked_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_invitation_role CHECK (intended_role IN ('municipal_officer','dept_admin','municipal_admin','system_admin')), 
	CONSTRAINT ck_invitation_status CHECK (status IN ('PENDING','ACCEPTED','EXPIRED','REVOKED')), 
	FOREIGN KEY(municipality_id) REFERENCES municipalities (id) ON DELETE SET NULL, 
	FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE SET NULL, 
	UNIQUE (token_hash), 
	FOREIGN KEY(invited_by_id) REFERENCES users (id) ON DELETE SET NULL
);

-- Table: citizen_visible_updates
CREATE TABLE IF NOT EXISTS citizen_visible_updates (
	id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36) NOT NULL, 
	published_by VARCHAR(36), 
	public_message TEXT NOT NULL, 
	status_label VARCHAR(50) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(published_by) REFERENCES users (id) ON DELETE SET NULL
);

-- Table: detection_embeddings
CREATE TABLE IF NOT EXISTS detection_embeddings (
	id VARCHAR(36) NOT NULL, 
	detection_id VARCHAR(36), 
	evidence_asset_id VARCHAR(36), 
	crop_bbox_json TEXT, 
	embedding_vector JSON, 
	embedding_model VARCHAR(100) NOT NULL, 
	embedding_model_version VARCHAR(50) NOT NULL, 
	embedding_dimension INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(detection_id) REFERENCES detections_v3 (id) ON DELETE CASCADE, 
	FOREIGN KEY(evidence_asset_id) REFERENCES evidence_assets_v2 (id) ON DELETE CASCADE
);

-- Table: incident_assignments
CREATE TABLE IF NOT EXISTS incident_assignments (
	id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36) NOT NULL, 
	department_id VARCHAR(36), 
	assigned_to VARCHAR(36), 
	status VARCHAR(20) NOT NULL, 
	priority VARCHAR(10), 
	notes TEXT, 
	assigned_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_assignment_status CHECK (status IN ('assigned','in_progress','completed','cancelled')), 
	CONSTRAINT ck_assignment_priority CHECK (priority IN ('low','normal','high','urgent')), 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(department_id) REFERENCES departments (id) ON DELETE SET NULL, 
	FOREIGN KEY(assigned_to) REFERENCES users (id) ON DELETE SET NULL
);

-- Table: incident_consolidations
CREATE TABLE IF NOT EXISTS incident_consolidations (
	id VARCHAR(36) NOT NULL, 
	canonical_incident_id VARCHAR(36) NOT NULL, 
	superseded_incident_id VARCHAR(36) NOT NULL, 
	consolidated_by VARCHAR(36) NOT NULL, 
	consolidation_reason TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_distinct_consolidations CHECK (canonical_incident_id != superseded_incident_id), 
	FOREIGN KEY(canonical_incident_id) REFERENCES incidents_v2 (id) ON DELETE RESTRICT, 
	FOREIGN KEY(superseded_incident_id) REFERENCES incidents_v2 (id) ON DELETE RESTRICT, 
	FOREIGN KEY(consolidated_by) REFERENCES users (id) ON DELETE RESTRICT
);

-- Table: incident_follows
CREATE TABLE IF NOT EXISTS incident_follows (
	id VARCHAR(36) NOT NULL, 
	citizen_id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36) NOT NULL, 
	notification_channels VARCHAR(100) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_citizen_incident_follow UNIQUE (citizen_id, incident_id), 
	FOREIGN KEY(citizen_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE
);

-- Table: incident_publications
CREATE TABLE IF NOT EXISTS incident_publications (
	id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36) NOT NULL, 
	visibility_status VARCHAR(30) NOT NULL, 
	published_at TIMESTAMP WITH TIME ZONE, 
	published_by VARCHAR(36), 
	public_title VARCHAR(255), 
	public_description TEXT, 
	public_location_name VARCHAR(255), 
	public_latitude FLOAT, 
	public_longitude FLOAT, 
	visibility_reason TEXT, 
	approved_evidence_ids TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_pub_visibility_status CHECK (visibility_status IN ('PRIVATE','PENDING_PUBLICATION','PUBLIC','HIDDEN','ARCHIVED')), 
	UNIQUE (incident_id), 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(published_by) REFERENCES users (id) ON DELETE SET NULL
);

-- Table: incident_status_history
CREATE TABLE IF NOT EXISTS incident_status_history (
	id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36) NOT NULL, 
	previous_status VARCHAR(20), 
	new_status VARCHAR(20) NOT NULL, 
	changed_by VARCHAR(36), 
	reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(changed_by) REFERENCES users (id) ON DELETE SET NULL
);

-- Table: inspection_records
CREATE TABLE IF NOT EXISTS inspection_records (
	id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36) NOT NULL, 
	officer_id VARCHAR(36), 
	inspection_date TIMESTAMP WITH TIME ZONE NOT NULL, 
	findings TEXT NOT NULL, 
	confirmed_defect_type VARCHAR(50) NOT NULL, 
	condition_rating VARCHAR(20) NOT NULL, 
	evidence_asset_id VARCHAR(36), 
	next_action VARCHAR(50) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_condition_rating CHECK (condition_rating IN ('minor','moderate','severe','critical')), 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(officer_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(evidence_asset_id) REFERENCES evidence_assets_v2 (id) ON DELETE SET NULL
);

-- Table: municipal_internal_notes
CREATE TABLE IF NOT EXISTS municipal_internal_notes (
	id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36) NOT NULL, 
	author_id VARCHAR(36), 
	content TEXT NOT NULL, 
	audience VARCHAR(30) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_note_audience CHECK (audience IN ('internal_officers','dept_admin_only','municipal_all')), 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE SET NULL
);

-- Table: report_items
CREATE TABLE IF NOT EXISTS report_items (
	id VARCHAR(36) NOT NULL, 
	report_id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36), 
	category VARCHAR(50) NOT NULL, 
	description TEXT, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_report_item_status CHECK (status IN ('pending','matched','new_incident','rejected')), 
	FOREIGN KEY(report_id) REFERENCES citizen_reports_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE SET NULL
);

-- Table: resolution_records
CREATE TABLE IF NOT EXISTS resolution_records (
	id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36) NOT NULL, 
	resolved_by VARCHAR(36), 
	resolution_notes TEXT NOT NULL, 
	before_evidence_id VARCHAR(36), 
	after_evidence_id VARCHAR(36), 
	resolved_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	approved_by VARCHAR(36), 
	approved_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (incident_id), 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(resolved_by) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(before_evidence_id) REFERENCES evidence_assets_v2 (id) ON DELETE SET NULL, 
	FOREIGN KEY(after_evidence_id) REFERENCES evidence_assets_v2 (id) ON DELETE SET NULL, 
	FOREIGN KEY(approved_by) REFERENCES users (id) ON DELETE SET NULL
);

-- Table: work_progress_updates
CREATE TABLE IF NOT EXISTS work_progress_updates (
	id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36) NOT NULL, 
	officer_id VARCHAR(36), 
	stage VARCHAR(50) NOT NULL, 
	notes TEXT, 
	hold_reason TEXT, 
	estimated_completion TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(officer_id) REFERENCES users (id) ON DELETE SET NULL
);

-- Table: ai_description_assistance
CREATE TABLE IF NOT EXISTS ai_description_assistance (
	id VARCHAR(36) NOT NULL, 
	report_id VARCHAR(36) NOT NULL, 
	report_item_id VARCHAR(36), 
	summary TEXT, 
	suggested_category VARCHAR(50), 
	missing_info_flags TEXT, 
	output_language VARCHAR(10) NOT NULL, 
	provider_name VARCHAR(50) NOT NULL, 
	model_name VARCHAR(100), 
	model_version VARCHAR(50), 
	processing_status VARCHAR(30) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(report_id) REFERENCES citizen_reports_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(report_item_id) REFERENCES report_items (id) ON DELETE SET NULL
);

-- Table: incident_observations_v2
CREATE TABLE IF NOT EXISTS incident_observations_v2 (
	id VARCHAR(36) NOT NULL, 
	incident_id VARCHAR(36) NOT NULL, 
	report_item_id VARCHAR(36), 
	detection_id VARCHAR(36), 
	evidence_asset_id VARCHAR(36), 
	observation_type VARCHAR(30) NOT NULL, 
	verification_status VARCHAR(20) NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_observation_verification CHECK (verification_status IN ('unverified','verified','disputed','superseded')), 
	FOREIGN KEY(incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(report_item_id) REFERENCES report_items (id) ON DELETE SET NULL, 
	FOREIGN KEY(detection_id) REFERENCES detections_v3 (id) ON DELETE SET NULL, 
	FOREIGN KEY(evidence_asset_id) REFERENCES evidence_assets_v2 (id) ON DELETE SET NULL
);

-- Table: match_evaluations
CREATE TABLE IF NOT EXISTS match_evaluations (
	id VARCHAR(36) NOT NULL, 
	report_item_id VARCHAR(36) NOT NULL, 
	matching_algorithm_version VARCHAR(50) NOT NULL, 
	processing_status VARCHAR(20) NOT NULL, 
	overall_decision VARCHAR(30) NOT NULL, 
	candidate_count INTEGER NOT NULL, 
	top_score FLOAT, 
	configuration_version VARCHAR(50) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_match_eval_status CHECK (processing_status IN ('pending','running','completed','failed')), 
	CONSTRAINT ck_match_eval_decision CHECK (overall_decision IN ('LIKELY_EXISTING_INCIDENT','NEEDS_HUMAN_CONFIRMATION','NEW_INCIDENT','INSUFFICIENT_EVIDENCE')), 
	FOREIGN KEY(report_item_id) REFERENCES report_items (id) ON DELETE CASCADE
);

-- Table: report_evidence
CREATE TABLE IF NOT EXISTS report_evidence (
	id VARCHAR(36) NOT NULL, 
	report_id VARCHAR(36) NOT NULL, 
	report_item_id VARCHAR(36), 
	evidence_asset_id VARCHAR(36) NOT NULL, 
	submitted_latitude FLOAT, 
	submitted_longitude FLOAT, 
	gps_source VARCHAR(30), 
	gps_accuracy_m FLOAT, 
	exif_latitude FLOAT, 
	exif_longitude FLOAT, 
	location_conflict BOOLEAN NOT NULL, 
	captured_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(report_id) REFERENCES citizen_reports_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(report_item_id) REFERENCES report_items (id) ON DELETE SET NULL, 
	FOREIGN KEY(evidence_asset_id) REFERENCES evidence_assets_v2 (id) ON DELETE RESTRICT
);

-- Table: report_translations
CREATE TABLE IF NOT EXISTS report_translations (
	id VARCHAR(36) NOT NULL, 
	report_id VARCHAR(36) NOT NULL, 
	report_item_id VARCHAR(36), 
	source_language VARCHAR(10) NOT NULL, 
	target_language VARCHAR(10) NOT NULL, 
	original_text TEXT NOT NULL, 
	translated_text TEXT, 
	provider_name VARCHAR(50) NOT NULL, 
	model_name VARCHAR(100), 
	model_version VARCHAR(50), 
	translation_status VARCHAR(30) NOT NULL, 
	review_status VARCHAR(30) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_trans_status CHECK (translation_status IN ('NOT_REQUESTED','PENDING','PROCESSING','COMPLETED','FAILED','NEEDS_REVIEW')), 
	CONSTRAINT ck_trans_review CHECK (review_status IN ('unreviewed','verified','corrected')), 
	FOREIGN KEY(report_id) REFERENCES citizen_reports_v2 (id) ON DELETE CASCADE, 
	FOREIGN KEY(report_item_id) REFERENCES report_items (id) ON DELETE SET NULL
);

-- Table: match_candidates
CREATE TABLE IF NOT EXISTS match_candidates (
	id VARCHAR(36) NOT NULL, 
	match_evaluation_id VARCHAR(36) NOT NULL, 
	candidate_incident_id VARCHAR(36) NOT NULL, 
	candidate_rank INTEGER NOT NULL, 
	combined_score FLOAT NOT NULL, 
	geographic_distance_m FLOAT, 
	geographic_score FLOAT, 
	visual_similarity_score FLOAT, 
	perceptual_similarity_score FLOAT, 
	exact_match_signal BOOLEAN NOT NULL, 
	category_score FLOAT, 
	text_score FLOAT, 
	decision_reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(match_evaluation_id) REFERENCES match_evaluations (id) ON DELETE CASCADE, 
	FOREIGN KEY(candidate_incident_id) REFERENCES incidents_v2 (id) ON DELETE CASCADE
);

-- Table: match_decisions_v2
CREATE TABLE IF NOT EXISTS match_decisions_v2 (
	id VARCHAR(36) NOT NULL, 
	match_evaluation_id VARCHAR(36), 
	report_item_id VARCHAR(36) NOT NULL, 
	candidate_incident_id VARCHAR(36), 
	visual_similarity_score FLOAT, 
	geographic_distance_m FLOAT, 
	category_similarity_score FLOAT, 
	overall_score FLOAT, 
	decision VARCHAR(30) NOT NULL, 
	decision_reason TEXT, 
	decision_source VARCHAR(30), 
	notes TEXT, 
	reviewed_by VARCHAR(36), 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_match_decision CHECK (decision IN ('LIKELY_EXISTING_INCIDENT','NEEDS_HUMAN_CONFIRMATION','NEW_INCIDENT','INSUFFICIENT_EVIDENCE')), 
	FOREIGN KEY(match_evaluation_id) REFERENCES match_evaluations (id) ON DELETE SET NULL, 
	FOREIGN KEY(report_item_id) REFERENCES report_items (id) ON DELETE CASCADE, 
	FOREIGN KEY(candidate_incident_id) REFERENCES incidents_v2 (id) ON DELETE SET NULL, 
	FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_v2_created ON audit_logs_v2 (created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_v2_entity ON audit_logs_v2 (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_v2_actor ON audit_logs_v2 (actor_id);
CREATE INDEX IF NOT EXISTS ix_evidence_phash ON evidence_assets_v2 (perceptual_hash);
CREATE INDEX IF NOT EXISTS ix_evidence_sha256_v2 ON evidence_assets_v2 (content_sha256);
CREATE UNIQUE INDEX IF NOT EXISTS ix_municipalities_code ON municipalities (code);
CREATE INDEX IF NOT EXISTS ix_notif_events_created ON notification_events (created_at);
CREATE INDEX IF NOT EXISTS ix_notif_events_status ON notification_events (processing_status);
CREATE INDEX IF NOT EXISTS ix_telem_device_id ON telemetry_devices (device_id);
CREATE INDEX IF NOT EXISTS ix_telem_device_status ON telemetry_devices (status);
CREATE INDEX IF NOT EXISTS ix_telem_device_heartbeat ON telemetry_devices (last_heartbeat_at);
CREATE INDEX IF NOT EXISTS ix_reports_v2_coords ON citizen_reports_v2 (latitude, longitude);
CREATE UNIQUE INDEX IF NOT EXISTS ix_citizen_reports_v2_idempotency_key ON citizen_reports_v2 (idempotency_key);
CREATE INDEX IF NOT EXISTS ix_reports_v2_citizen ON citizen_reports_v2 (citizen_id);
CREATE INDEX IF NOT EXISTS ix_reports_v2_status ON citizen_reports_v2 (status);
CREATE UNIQUE INDEX IF NOT EXISTS ix_departments_code ON departments (code);
CREATE INDEX IF NOT EXISTS ix_detection_runs_status ON detection_runs (processing_status);
CREATE INDEX IF NOT EXISTS ix_detection_runs_evidence ON detection_runs (evidence_asset_id);
CREATE INDEX IF NOT EXISTS ix_notif_deliv_recipient ON notification_deliveries (recipient_id);
CREATE INDEX IF NOT EXISTS ix_notif_deliv_status ON notification_deliveries (delivery_status);
CREATE INDEX IF NOT EXISTS ix_notif_deliv_event ON notification_deliveries (event_id);
CREATE INDEX IF NOT EXISTS ix_notif_pref_user ON notification_preferences (user_id);
CREATE INDEX IF NOT EXISTS ix_telem_severity ON telemetry_events (severity);
CREATE INDEX IF NOT EXISTS ix_telem_coords ON telemetry_events (latitude, longitude);
CREATE INDEX IF NOT EXISTS ix_telem_dev_ingested ON telemetry_events (device_id, ingested_at);
CREATE INDEX IF NOT EXISTS ix_user_notif_unread ON user_notifications (recipient_id, is_read);
CREATE INDEX IF NOT EXISTS ix_user_notif_created ON user_notifications (created_at);
CREATE INDEX IF NOT EXISTS ix_user_notif_recipient ON user_notifications (recipient_id);
CREATE INDEX IF NOT EXISTS ix_push_sub_user ON web_push_subscriptions (user_id);
CREATE INDEX IF NOT EXISTS ix_dept_memberships_user ON department_memberships (user_id);
CREATE INDEX IF NOT EXISTS ix_dept_memberships_dept ON department_memberships (department_id);
CREATE INDEX IF NOT EXISTS ix_detections_v3_run ON detections_v3 (detection_run_id);
CREATE INDEX IF NOT EXISTS ix_detections_v3_evidence ON detections_v3 (evidence_asset_id);
CREATE INDEX IF NOT EXISTS ix_incidents_v2_coords ON incidents_v2 (latitude, longitude);
CREATE INDEX IF NOT EXISTS ix_incidents_v2_severity ON incidents_v2 (severity);
CREATE INDEX IF NOT EXISTS ix_incidents_v2_officer ON incidents_v2 (assigned_officer_id);
CREATE INDEX IF NOT EXISTS ix_incidents_v2_category ON incidents_v2 (category);
CREATE INDEX IF NOT EXISTS ix_incidents_v2_status ON incidents_v2 (status);
CREATE INDEX IF NOT EXISTS ix_incidents_v2_dept ON incidents_v2 (department_id);
CREATE INDEX IF NOT EXISTS ix_incidents_v2_priority ON incidents_v2 (priority);
CREATE INDEX IF NOT EXISTS ix_loc_records_coords ON location_records (latitude, longitude);
CREATE INDEX IF NOT EXISTS ix_invitations_token_hash ON official_invitations (token_hash);
CREATE INDEX IF NOT EXISTS ix_invitations_email ON official_invitations (invited_email);
CREATE INDEX IF NOT EXISTS ix_invitations_status ON official_invitations (status);
CREATE INDEX IF NOT EXISTS ix_citizen_updates_incident ON citizen_visible_updates (incident_id);
CREATE INDEX IF NOT EXISTS ix_detection_embeddings_det ON detection_embeddings (detection_id);
CREATE INDEX IF NOT EXISTS ix_detection_embeddings_asset ON detection_embeddings (evidence_asset_id);
CREATE INDEX IF NOT EXISTS ix_assignments_incident ON incident_assignments (incident_id);
CREATE INDEX IF NOT EXISTS ix_assignments_dept ON incident_assignments (department_id);
CREATE INDEX IF NOT EXISTS ix_consolidation_superseded ON incident_consolidations (superseded_incident_id);
CREATE INDEX IF NOT EXISTS ix_consolidation_canonical ON incident_consolidations (canonical_incident_id);
CREATE INDEX IF NOT EXISTS ix_follows_citizen ON incident_follows (citizen_id);
CREATE INDEX IF NOT EXISTS ix_follows_incident ON incident_follows (incident_id);
CREATE INDEX IF NOT EXISTS ix_inc_pub_coords ON incident_publications (public_latitude, public_longitude);
CREATE INDEX IF NOT EXISTS ix_inc_pub_visibility ON incident_publications (visibility_status);
CREATE INDEX IF NOT EXISTS ix_status_history_incident ON incident_status_history (incident_id);
CREATE INDEX IF NOT EXISTS ix_inspection_incident ON inspection_records (incident_id);
CREATE INDEX IF NOT EXISTS ix_internal_notes_incident ON municipal_internal_notes (incident_id);
CREATE INDEX IF NOT EXISTS ix_report_items_incident ON report_items (incident_id);
CREATE INDEX IF NOT EXISTS ix_report_items_report ON report_items (report_id);
CREATE INDEX IF NOT EXISTS ix_resolution_incident ON resolution_records (incident_id);
CREATE INDEX IF NOT EXISTS ix_work_progress_incident ON work_progress_updates (incident_id);
CREATE INDEX IF NOT EXISTS ix_ai_assist_report ON ai_description_assistance (report_id);
CREATE INDEX IF NOT EXISTS ix_observations_v2_incident ON incident_observations_v2 (incident_id);
CREATE INDEX IF NOT EXISTS ix_match_eval_item ON match_evaluations (report_item_id);
CREATE INDEX IF NOT EXISTS ix_report_evidence_report ON report_evidence (report_id);
CREATE INDEX IF NOT EXISTS ix_report_evidence_asset ON report_evidence (evidence_asset_id);
CREATE INDEX IF NOT EXISTS ix_trans_report ON report_translations (report_id);
CREATE INDEX IF NOT EXISTS ix_trans_status ON report_translations (translation_status);
CREATE INDEX IF NOT EXISTS ix_match_candidates_eval ON match_candidates (match_evaluation_id);
CREATE INDEX IF NOT EXISTS ix_match_candidates_incident ON match_candidates (candidate_incident_id);
CREATE INDEX IF NOT EXISTS ix_match_decisions_v2_item ON match_decisions_v2 (report_item_id);
CREATE INDEX IF NOT EXISTS ix_match_decisions_v2_eval ON match_decisions_v2 (match_evaluation_id);
CREATE INDEX IF NOT EXISTS ix_match_decisions_v2_incident ON match_decisions_v2 (candidate_incident_id);