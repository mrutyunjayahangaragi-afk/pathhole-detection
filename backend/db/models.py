"""
CivicLens SQLAlchemy ORM Models
================================
Normalized schema supporting the full CivicLens domain:
- Users, Incidents, CitizenReports, ReportItems, EvidenceAssets
- DetectionRuns, Detections, IncidentObservations, MatchDecisions
- IncidentStatusHistory, Departments, IncidentAssignments, AuditLogs
"""

import uuid
import time
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean, DateTime,
    ForeignKey, CheckConstraint, UniqueConstraint, Index,
    Numeric, JSON, func,
)
from sqlalchemy.orm import declarative_base, relationship
from typing import Optional

Base = declarative_base()


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── Users / Profiles ────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    display_name = Column(String(255), nullable=False, default="")
    email = Column(String(320), nullable=True, unique=True)
    phone = Column(String(20), nullable=True)
    role = Column(
        String(30), nullable=False, default="citizen",
    )
    preferred_language = Column(String(5), nullable=False, default="en")
    password_hash = Column(String(255), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    reports = relationship("CitizenReport", back_populates="citizen", lazy="dynamic")
    department_memberships = relationship("DepartmentMembership", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "role IN ('citizen','municipal_officer','dept_admin','municipal_admin','system_admin')",
            name="ck_users_role"
        ),
    )


# ─── Incidents ────────────────────────────────────────────────────────

class Incident(Base):
    __tablename__ = "incidents_v2"

    id = Column(String(36), primary_key=True, default=_uuid)
    incident_reference = Column(String(20), unique=True, nullable=True)
    category = Column(String(50), nullable=False, default="pothole")
    description = Column(Text, nullable=True)
    severity = Column(String(10), nullable=False, default="minor")
    priority = Column(String(10), nullable=False, default="normal")
    status = Column(String(20), nullable=False, default="reported")

    # Department & Officer Assignment
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    assigned_officer_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Location — stored as lat/lon floats for SQLite compat
    # PostGIS geography column added via Alembic migration when on PostgreSQL
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_accuracy_m = Column(Float, nullable=True)
    address = Column(Text, nullable=True)

    report_count = Column(Integer, nullable=False, default=1)
    est_depth_cm = Column(Float, nullable=True, default=0.0)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    reopened_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    department = relationship("Department", back_populates="incidents", foreign_keys=[department_id])
    assigned_officer = relationship("User", foreign_keys=[assigned_officer_id])
    report_items = relationship("ReportItem", back_populates="incident", lazy="dynamic")
    observations = relationship("IncidentObservation", back_populates="incident", lazy="dynamic")
    status_history = relationship("IncidentStatusHistory", back_populates="incident", lazy="dynamic")
    assignments = relationship("IncidentAssignment", back_populates="incident", lazy="dynamic")
    inspections = relationship("InspectionRecord", back_populates="incident", cascade="all, delete-orphan")
    work_progress = relationship("WorkProgressUpdate", back_populates="incident", cascade="all, delete-orphan")
    resolution = relationship("ResolutionRecord", back_populates="incident", uselist=False, cascade="all, delete-orphan")
    internal_notes = relationship("MunicipalInternalNote", back_populates="incident", cascade="all, delete-orphan")
    citizen_updates = relationship("CitizenVisibleUpdate", back_populates="incident", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "severity IN ('minor','moderate','severe','critical')",
            name="ck_incident_severity"
        ),
        CheckConstraint(
            "priority IN ('low','normal','high','critical')",
            name="ck_incident_priority"
        ),
        CheckConstraint(
            "status IN ('new','awaiting_verification','verified','assigned','in_progress','on_hold','resolved','reopened','closed','rejected','reported','acknowledged','scheduled','repaired')",
            name="ck_incident_status"
        ),
        CheckConstraint(
            "category IN ('pothole','road_damage','bridge_damage','garbage','water_leakage','drainage','broken_streetlight','other')",
            name="ck_incident_category"
        ),
        Index("ix_incidents_v2_coords", "latitude", "longitude"),
        Index("ix_incidents_v2_status", "status"),
        Index("ix_incidents_v2_severity", "severity"),
        Index("ix_incidents_v2_priority", "priority"),
        Index("ix_incidents_v2_category", "category"),
        Index("ix_incidents_v2_dept", "department_id"),
        Index("ix_incidents_v2_officer", "assigned_officer_id"),
    )


# ─── Citizen Reports ─────────────────────────────────────────────────

class CitizenReport(Base):
    __tablename__ = "citizen_reports_v2"

    id = Column(String(36), primary_key=True, default=_uuid)
    citizen_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    report_reference = Column(String(20), unique=True, nullable=True)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    reported_severity = Column(String(20), nullable=True, default="minor")
    idempotency_key = Column(String(64), nullable=True, unique=True, index=True)
    is_manual_location = Column(Boolean, nullable=False, default=False)
    latitude = Column(Float, nullable=False, default=0.0)
    longitude = Column(Float, nullable=False, default=0.0)
    location_accuracy_m = Column(Float, nullable=True)
    address = Column(Text, nullable=True)
    original_language = Column(String(5), nullable=False, default="en")
    translated_description = Column(Text, nullable=True)
    detected_language = Column(String(10), nullable=True)
    language_detection_confidence = Column(Float, nullable=True)
    language_detection_model = Column(String(50), nullable=True)
    language_detection_status = Column(String(30), nullable=False, default="pending")
    submission_channel = Column(String(30), nullable=False, default="web")
    status = Column(String(20), nullable=False, default="submitted")

    submitted_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    citizen = relationship("User", back_populates="reports")
    items = relationship("ReportItem", back_populates="report", cascade="all, delete-orphan")
    evidence_links = relationship("ReportEvidence", back_populates="report", cascade="all, delete-orphan")
    translations = relationship("ReportTranslation", back_populates="report", cascade="all, delete-orphan")
    description_assistance = relationship("AIDescriptionAssistance", back_populates="report", cascade="all, delete-orphan")
    location_record = relationship("LocationRecord", back_populates="report", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "submission_channel IN ('mobile_app','web','vehicle_telematics','manual_official','phone_call')",
            name="ck_report_channel"
        ),
        CheckConstraint(
            "status IN ('submitted','under_review','linked','rejected','withdrawn','acknowledged','resolved')",
            name="ck_report_status"
        ),
        CheckConstraint(
            "reported_severity IS NULL OR reported_severity IN ('minor','moderate','severe','critical')",
            name="ck_report_severity"
        ),
        Index("ix_reports_v2_citizen", "citizen_id"),
        Index("ix_reports_v2_status", "status"),
        Index("ix_reports_v2_coords", "latitude", "longitude"),
    )


# ─── Report Items ────────────────────────────────────────────────────

class ReportItem(Base):
    __tablename__ = "report_items"

    id = Column(String(36), primary_key=True, default=_uuid)
    report_id = Column(String(36), ForeignKey("citizen_reports_v2.id", ondelete="CASCADE"), nullable=False)
    incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="SET NULL"), nullable=True)
    category = Column(String(50), nullable=False, default="pothole")
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    report = relationship("CitizenReport", back_populates="items")
    incident = relationship("Incident", back_populates="report_items")
    match_decisions = relationship("MatchDecision", back_populates="report_item", lazy="dynamic")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','matched','new_incident','rejected')",
            name="ck_report_item_status"
        ),
        Index("ix_report_items_report", "report_id"),
        Index("ix_report_items_incident", "incident_id"),
    )


# ─── Evidence Assets ─────────────────────────────────────────────────

class EvidenceAsset(Base):
    __tablename__ = "evidence_assets_v2"

    id = Column(String(36), primary_key=True, default=_uuid)
    content_sha256 = Column(String(64), nullable=True, unique=True)
    perceptual_hash = Column(String(64), nullable=True)
    hash_algorithm = Column(String(30), nullable=True, default="dct_phash")
    hash_version = Column(String(20), nullable=True, default="v1.0")
    storage_key = Column(Text, nullable=True)
    media_type = Column(String(50), nullable=True)
    file_size_bytes = Column(Integer, nullable=True, default=0)
    original_filename = Column(String(255), nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    report_links = relationship("ReportEvidence", back_populates="evidence_asset")
    detection_runs = relationship("DetectionRun", back_populates="evidence_asset", lazy="dynamic")
    embeddings = relationship("DetectionEmbedding", back_populates="evidence_asset", lazy="dynamic")

    __table_args__ = (
        Index("ix_evidence_sha256_v2", "content_sha256"),
        Index("ix_evidence_phash", "perceptual_hash"),
    )


# ─── Report Evidence (association) ───────────────────────────────────

class ReportEvidence(Base):
    __tablename__ = "report_evidence"

    id = Column(String(36), primary_key=True, default=_uuid)
    report_id = Column(String(36), ForeignKey("citizen_reports_v2.id", ondelete="CASCADE"), nullable=False)
    report_item_id = Column(String(36), ForeignKey("report_items.id", ondelete="SET NULL"), nullable=True)
    evidence_asset_id = Column(String(36), ForeignKey("evidence_assets_v2.id", ondelete="RESTRICT"), nullable=False)

    submitted_latitude = Column(Float, nullable=True)
    submitted_longitude = Column(Float, nullable=True)
    gps_source = Column(String(30), nullable=True)
    gps_accuracy_m = Column(Float, nullable=True)
    exif_latitude = Column(Float, nullable=True)
    exif_longitude = Column(Float, nullable=True)
    location_conflict = Column(Boolean, nullable=False, default=False)
    captured_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    report = relationship("CitizenReport", back_populates="evidence_links")
    evidence_asset = relationship("EvidenceAsset", back_populates="report_links")

    __table_args__ = (
        Index("ix_report_evidence_report", "report_id"),
        Index("ix_report_evidence_asset", "evidence_asset_id"),
    )


# ─── Detection Runs ──────────────────────────────────────────────────

class DetectionRun(Base):
    __tablename__ = "detection_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    evidence_asset_id = Column(String(36), ForeignKey("evidence_assets_v2.id", ondelete="CASCADE"), nullable=False)
    model_name = Column(String(100), nullable=False, default="yolov8")
    model_version = Column(String(50), nullable=False, default="baseline")
    processing_status = Column(String(20), nullable=False, default="pending")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    processing_duration_ms = Column(Float, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    evidence_asset = relationship("EvidenceAsset", back_populates="detection_runs")
    detections = relationship("Detection", back_populates="detection_run", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('pending','processing','running','completed','failed','needs_review')",
            name="ck_detection_run_status"
        ),
        Index("ix_detection_runs_evidence", "evidence_asset_id"),
        Index("ix_detection_runs_status", "processing_status"),
    )


# ─── Detections ───────────────────────────────────────────────────────

class Detection(Base):
    __tablename__ = "detections_v3"

    id = Column(String(36), primary_key=True, default=_uuid)
    detection_run_id = Column(String(36), ForeignKey("detection_runs.id", ondelete="CASCADE"), nullable=False)
    evidence_asset_id = Column(String(36), ForeignKey("evidence_assets_v2.id", ondelete="CASCADE"), nullable=True)
    detected_category = Column(String(50), nullable=False, default="pothole")
    confidence_score = Column(Float, nullable=False, default=0.0)
    confidence_tier = Column(String(20), nullable=True, default="medium")

    # Absolute pixel coordinates
    bbox_x = Column(Integer, nullable=True, default=0)
    bbox_y = Column(Integer, nullable=True, default=0)
    bbox_w = Column(Integer, nullable=True, default=0)
    bbox_h = Column(Integer, nullable=True, default=0)

    # Normalized [0.0, 1.0] coordinates
    normalized_xmin = Column(Float, nullable=True)
    normalized_ymin = Column(Float, nullable=True)
    normalized_xmax = Column(Float, nullable=True)
    normalized_ymax = Column(Float, nullable=True)

    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)

    est_depth_cm = Column(Float, nullable=True)
    severity = Column(String(10), nullable=True)
    model_version = Column(String(50), nullable=True)
    review_status = Column(String(20), nullable=False, default="unreviewed")
    reviewed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    detection_run = relationship("DetectionRun", back_populates="detections")
    embedding = relationship("DetectionEmbedding", back_populates="detection", uselist=False)

    __table_args__ = (
        CheckConstraint("confidence_score BETWEEN 0.0 AND 1.0", name="ck_detection_confidence"),
        CheckConstraint(
            "review_status IN ('unreviewed','confirmed','rejected','uncertain','corrected')",
            name="ck_detection_review_status"
        ),
        Index("ix_detections_v3_run", "detection_run_id"),
        Index("ix_detections_v3_evidence", "evidence_asset_id"),
    )


# ─── Incident Observations ───────────────────────────────────────────

class IncidentObservation(Base):
    __tablename__ = "incident_observations_v2"

    id = Column(String(36), primary_key=True, default=_uuid)
    incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="CASCADE"), nullable=False)
    report_item_id = Column(String(36), ForeignKey("report_items.id", ondelete="SET NULL"), nullable=True)
    detection_id = Column(String(36), ForeignKey("detections_v3.id", ondelete="SET NULL"), nullable=True)
    evidence_asset_id = Column(String(36), ForeignKey("evidence_assets_v2.id", ondelete="SET NULL"), nullable=True)
    observation_type = Column(String(30), nullable=False, default="citizen_report")
    verification_status = Column(String(20), nullable=False, default="unverified")
    observed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    incident = relationship("Incident", back_populates="observations")

    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('unverified','verified','disputed','superseded')",
            name="ck_observation_verification"
        ),
        Index("ix_observations_v2_incident", "incident_id"),
    )


# ─── Detection Embeddings ─────────────────────────────────────────────

class DetectionEmbedding(Base):
    __tablename__ = "detection_embeddings"

    id = Column(String(36), primary_key=True, default=_uuid)
    detection_id = Column(String(36), ForeignKey("detections_v3.id", ondelete="CASCADE"), nullable=True)
    evidence_asset_id = Column(String(36), ForeignKey("evidence_assets_v2.id", ondelete="CASCADE"), nullable=True)
    crop_bbox_json = Column(Text, nullable=True)
    embedding_vector = Column(JSON, nullable=True)
    embedding_model = Column(String(100), nullable=False, default="mock_embedding")
    embedding_model_version = Column(String(50), nullable=False, default="v1.0")
    embedding_dimension = Column(Integer, nullable=False, default=128)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    detection = relationship("Detection", back_populates="embedding")
    evidence_asset = relationship("EvidenceAsset", back_populates="embeddings")

    __table_args__ = (
        Index("ix_detection_embeddings_det", "detection_id"),
        Index("ix_detection_embeddings_asset", "evidence_asset_id"),
    )


# ─── Match Evaluations ───────────────────────────────────────────────

class MatchEvaluation(Base):
    __tablename__ = "match_evaluations"

    id = Column(String(36), primary_key=True, default=_uuid)
    report_item_id = Column(String(36), ForeignKey("report_items.id", ondelete="CASCADE"), nullable=False)
    matching_algorithm_version = Column(String(50), nullable=False, default="v1.0.0")
    processing_status = Column(String(20), nullable=False, default="completed")
    overall_decision = Column(String(30), nullable=False)
    candidate_count = Column(Integer, nullable=False, default=0)
    top_score = Column(Float, nullable=True)
    configuration_version = Column(String(50), nullable=False, default="v1.0")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    candidates = relationship("MatchCandidate", back_populates="evaluation", cascade="all, delete-orphan")
    decisions = relationship("MatchDecision", back_populates="evaluation")

    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('pending','running','completed','failed')",
            name="ck_match_eval_status"
        ),
        CheckConstraint(
            "overall_decision IN ('LIKELY_EXISTING_INCIDENT','NEEDS_HUMAN_CONFIRMATION','NEW_INCIDENT','INSUFFICIENT_EVIDENCE')",
            name="ck_match_eval_decision"
        ),
        Index("ix_match_eval_item", "report_item_id"),
    )


# ─── Match Candidates ────────────────────────────────────────────────

class MatchCandidate(Base):
    __tablename__ = "match_candidates"

    id = Column(String(36), primary_key=True, default=_uuid)
    match_evaluation_id = Column(String(36), ForeignKey("match_evaluations.id", ondelete="CASCADE"), nullable=False)
    candidate_incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="CASCADE"), nullable=False)
    candidate_rank = Column(Integer, nullable=False, default=1)
    combined_score = Column(Float, nullable=False, default=0.0)
    geographic_distance_m = Column(Float, nullable=True)
    geographic_score = Column(Float, nullable=True)
    visual_similarity_score = Column(Float, nullable=True)
    perceptual_similarity_score = Column(Float, nullable=True)
    exact_match_signal = Column(Boolean, nullable=False, default=False)
    category_score = Column(Float, nullable=True)
    text_score = Column(Float, nullable=True)
    decision_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    evaluation = relationship("MatchEvaluation", back_populates="candidates")
    candidate_incident = relationship("Incident")

    __table_args__ = (
        Index("ix_match_candidates_eval", "match_evaluation_id"),
        Index("ix_match_candidates_incident", "candidate_incident_id"),
    )


# ─── Match Decisions ─────────────────────────────────────────────────

class MatchDecision(Base):
    __tablename__ = "match_decisions_v2"

    id = Column(String(36), primary_key=True, default=_uuid)
    match_evaluation_id = Column(String(36), ForeignKey("match_evaluations.id", ondelete="SET NULL"), nullable=True)
    report_item_id = Column(String(36), ForeignKey("report_items.id", ondelete="CASCADE"), nullable=False)
    candidate_incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="SET NULL"), nullable=True)
    visual_similarity_score = Column(Float, nullable=True)
    geographic_distance_m = Column(Float, nullable=True)
    category_similarity_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    decision = Column(String(30), nullable=False)
    decision_reason = Column(Text, nullable=True)
    decision_source = Column(String(30), nullable=True, default="human_reviewer")
    notes = Column(Text, nullable=True)
    reviewed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    report_item = relationship("ReportItem", back_populates="match_decisions")
    evaluation = relationship("MatchEvaluation", back_populates="decisions")

    __table_args__ = (
        CheckConstraint(
            "decision IN ('LIKELY_EXISTING_INCIDENT','NEEDS_HUMAN_CONFIRMATION','NEW_INCIDENT','INSUFFICIENT_EVIDENCE')",
            name="ck_match_decision"
        ),
        Index("ix_match_decisions_v2_item", "report_item_id"),
        Index("ix_match_decisions_v2_incident", "candidate_incident_id"),
        Index("ix_match_decisions_v2_eval", "match_evaluation_id"),
    )


# ─── Incident Consolidations ─────────────────────────────────────────

class IncidentConsolidation(Base):
    __tablename__ = "incident_consolidations"

    id = Column(String(36), primary_key=True, default=_uuid)
    canonical_incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="RESTRICT"), nullable=False)
    superseded_incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="RESTRICT"), nullable=False)
    consolidated_by = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    consolidation_reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    canonical_incident = relationship("Incident", foreign_keys=[canonical_incident_id])
    superseded_incident = relationship("Incident", foreign_keys=[superseded_incident_id])
    consolidator = relationship("User", foreign_keys=[consolidated_by])

    __table_args__ = (
        CheckConstraint(
            "canonical_incident_id != superseded_incident_id",
            name="ck_distinct_consolidations"
        ),
        Index("ix_consolidation_canonical", "canonical_incident_id"),
        Index("ix_consolidation_superseded", "superseded_incident_id"),
    )


# ─── Incident Status History ─────────────────────────────────────────

class IncidentStatusHistory(Base):
    __tablename__ = "incident_status_history"

    id = Column(String(36), primary_key=True, default=_uuid)
    incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="CASCADE"), nullable=False)
    previous_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    changed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    incident = relationship("Incident", back_populates="status_history")

    __table_args__ = (
        Index("ix_status_history_incident", "incident_id"),
    )


# ─── Departments ──────────────────────────────────────────────────────

class Department(Base):
    __tablename__ = "departments"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False, unique=True)
    code = Column(String(50), nullable=True, unique=True, index=True)
    description = Column(Text, nullable=True)
    contact_email = Column(String(320), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    assignments = relationship("IncidentAssignment", back_populates="department", lazy="dynamic")
    memberships = relationship("DepartmentMembership", back_populates="department", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="department", foreign_keys="Incident.department_id")


# ─── Department Memberships ──────────────────────────────────────────

class DepartmentMembership(Base):
    __tablename__ = "department_memberships"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    role_in_dept = Column(String(30), nullable=False, default="officer")
    is_active = Column(Boolean, nullable=False, default=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="department_memberships")
    department = relationship("Department", back_populates="memberships")

    __table_args__ = (
        CheckConstraint(
            "role_in_dept IN ('officer','lead','admin')",
            name="ck_dept_member_role"
        ),
        UniqueConstraint("user_id", "department_id", name="uq_user_dept"),
        Index("ix_dept_memberships_user", "user_id"),
        Index("ix_dept_memberships_dept", "department_id"),
    )


# ─── Inspection Records ──────────────────────────────────────────────

class InspectionRecord(Base):
    __tablename__ = "inspection_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="CASCADE"), nullable=False)
    officer_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    inspection_date = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    findings = Column(Text, nullable=False)
    confirmed_defect_type = Column(String(50), nullable=False)
    condition_rating = Column(String(20), nullable=False, default="moderate")
    evidence_asset_id = Column(String(36), ForeignKey("evidence_assets_v2.id", ondelete="SET NULL"), nullable=True)
    next_action = Column(String(50), nullable=False, default="schedule_repair")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    incident = relationship("Incident", back_populates="inspections")
    officer = relationship("User", foreign_keys=[officer_id])
    evidence_asset = relationship("EvidenceAsset", foreign_keys=[evidence_asset_id])

    __table_args__ = (
        CheckConstraint(
            "condition_rating IN ('minor','moderate','severe','critical')",
            name="ck_condition_rating"
        ),
        Index("ix_inspection_incident", "incident_id"),
    )


# ─── Work Progress Updates ───────────────────────────────────────────

class WorkProgressUpdate(Base):
    __tablename__ = "work_progress_updates"

    id = Column(String(36), primary_key=True, default=_uuid)
    incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="CASCADE"), nullable=False)
    officer_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    stage = Column(String(50), nullable=False)
    notes = Column(Text, nullable=True)
    hold_reason = Column(Text, nullable=True)
    estimated_completion = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    incident = relationship("Incident", back_populates="work_progress")
    officer = relationship("User", foreign_keys=[officer_id])

    __table_args__ = (
        Index("ix_work_progress_incident", "incident_id"),
    )


# ─── Resolution Records ──────────────────────────────────────────────

class ResolutionRecord(Base):
    __tablename__ = "resolution_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="CASCADE"), nullable=False, unique=True)
    resolved_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=False)
    before_evidence_id = Column(String(36), ForeignKey("evidence_assets_v2.id", ondelete="SET NULL"), nullable=True)
    after_evidence_id = Column(String(36), ForeignKey("evidence_assets_v2.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    approved_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    incident = relationship("Incident", back_populates="resolution")
    resolver = relationship("User", foreign_keys=[resolved_by])
    approver = relationship("User", foreign_keys=[approved_by])
    before_evidence = relationship("EvidenceAsset", foreign_keys=[before_evidence_id])
    after_evidence = relationship("EvidenceAsset", foreign_keys=[after_evidence_id])

    __table_args__ = (
        Index("ix_resolution_incident", "incident_id"),
    )


# ─── Municipal Internal Notes ─────────────────────────────────────────

class MunicipalInternalNote(Base):
    __tablename__ = "municipal_internal_notes"

    id = Column(String(36), primary_key=True, default=_uuid)
    incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    content = Column(Text, nullable=False)
    audience = Column(String(30), nullable=False, default="internal_officers")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    incident = relationship("Incident", back_populates="internal_notes")
    author = relationship("User", foreign_keys=[author_id])

    __table_args__ = (
        CheckConstraint(
            "audience IN ('internal_officers','dept_admin_only','municipal_all')",
            name="ck_note_audience"
        ),
        Index("ix_internal_notes_incident", "incident_id"),
    )


# ─── Citizen Visible Updates ──────────────────────────────────────────

class CitizenVisibleUpdate(Base):
    __tablename__ = "citizen_visible_updates"

    id = Column(String(36), primary_key=True, default=_uuid)
    incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="CASCADE"), nullable=False)
    published_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    public_message = Column(Text, nullable=False)
    status_label = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    incident = relationship("Incident", back_populates="citizen_updates")
    publisher = relationship("User", foreign_keys=[published_by])

    __table_args__ = (
        Index("ix_citizen_updates_incident", "incident_id"),
    )


# ─── Incident Assignments ────────────────────────────────────────────

class IncidentAssignment(Base):
    __tablename__ = "incident_assignments"

    id = Column(String(36), primary_key=True, default=_uuid)
    incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    assigned_to = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="assigned")
    priority = Column(String(10), nullable=True, default="normal")
    notes = Column(Text, nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    incident = relationship("Incident", back_populates="assignments")
    department = relationship("Department", back_populates="assignments")

    __table_args__ = (
        CheckConstraint(
            "status IN ('assigned','in_progress','completed','cancelled')",
            name="ck_assignment_status"
        ),
        CheckConstraint(
            "priority IN ('low','normal','high','urgent')",
            name="ck_assignment_priority"
        ),
        Index("ix_assignments_incident", "incident_id"),
        Index("ix_assignments_dept", "department_id"),
    )



# ─── Multilingual Translations ───────────────────────────────────────

class ReportTranslation(Base):
    __tablename__ = "report_translations"

    id = Column(String(36), primary_key=True, default=_uuid)
    report_id = Column(String(36), ForeignKey("citizen_reports_v2.id", ondelete="CASCADE"), nullable=False)
    report_item_id = Column(String(36), ForeignKey("report_items.id", ondelete="SET NULL"), nullable=True)
    source_language = Column(String(10), nullable=False)
    target_language = Column(String(10), nullable=False)
    original_text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=True)
    provider_name = Column(String(50), nullable=False, default="civic_rule_dict")
    model_name = Column(String(100), nullable=True)
    model_version = Column(String(50), nullable=True)
    translation_status = Column(String(30), nullable=False, default="COMPLETED")
    review_status = Column(String(30), nullable=False, default="unreviewed")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    report = relationship("CitizenReport", back_populates="translations")

    __table_args__ = (
        CheckConstraint(
            "translation_status IN ('NOT_REQUESTED','PENDING','PROCESSING','COMPLETED','FAILED','NEEDS_REVIEW')",
            name="ck_trans_status"
        ),
        CheckConstraint(
            "review_status IN ('unreviewed','verified','corrected')",
            name="ck_trans_review"
        ),
        Index("ix_trans_report", "report_id"),
        Index("ix_trans_status", "translation_status"),
    )


# ─── AI Description Assistance ────────────────────────────────────────

class AIDescriptionAssistance(Base):
    __tablename__ = "ai_description_assistance"

    id = Column(String(36), primary_key=True, default=_uuid)
    report_id = Column(String(36), ForeignKey("citizen_reports_v2.id", ondelete="CASCADE"), nullable=False)
    report_item_id = Column(String(36), ForeignKey("report_items.id", ondelete="SET NULL"), nullable=True)
    summary = Column(Text, nullable=True)
    suggested_category = Column(String(50), nullable=True)
    missing_info_flags = Column(Text, nullable=True)  # JSON-encoded array
    output_language = Column(String(10), nullable=False, default="en")
    provider_name = Column(String(50), nullable=False, default="civic_rule_assist")
    model_name = Column(String(100), nullable=True)
    model_version = Column(String(50), nullable=True)
    processing_status = Column(String(30), nullable=False, default="completed")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    report = relationship("CitizenReport", back_populates="description_assistance")

    __table_args__ = (
        Index("ix_ai_assist_report", "report_id"),
    )


# ─── Location Records & Provenance ────────────────────────────────────

class LocationRecord(Base):
    __tablename__ = "location_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    report_id = Column(String(36), ForeignKey("citizen_reports_v2.id", ondelete="CASCADE"), nullable=False, unique=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_accuracy_m = Column(Float, nullable=True)
    location_source = Column(String(30), nullable=False, default="manual_pin")
    road_name = Column(String(255), nullable=True)
    road_type = Column(String(50), nullable=True)
    locality = Column(String(255), nullable=True)
    suburb = Column(String(255), nullable=True)
    city = Column(String(255), nullable=True)
    district = Column(String(255), nullable=True)
    state = Column(String(255), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True)
    normalized_address = Column(Text, nullable=True)
    raw_geocoding_json = Column(Text, nullable=True)
    geocoding_provider = Column(String(50), nullable=False, default="nominatim")
    geocoding_status = Column(String(30), nullable=False, default="pending")
    geocoded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    report = relationship("CitizenReport", back_populates="location_record")

    __table_args__ = (
        CheckConstraint(
            "location_source IN ('device_gps','manual_pin','exif_gps','citizen_text')",
            name="ck_loc_source"
        ),
        Index("ix_loc_records_coords", "latitude", "longitude"),
    )


# ─── Audit Logs ──────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs_v2"

    id = Column(String(36), primary_key=True, default=_uuid)
    actor_id = Column(String(36), nullable=True)
    action = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(36), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_audit_logs_v2_entity", "entity_type", "entity_id"),
        Index("ix_audit_logs_v2_actor", "actor_id"),
        Index("ix_audit_logs_v2_created", "created_at"),
    )
