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
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    reports = relationship("CitizenReport", back_populates="citizen", lazy="dynamic")

    __table_args__ = (
        CheckConstraint(
            "role IN ('citizen','municipal_officer','dept_admin','system_admin')",
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
    status = Column(String(20), nullable=False, default="reported")

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
    report_items = relationship("ReportItem", back_populates="incident", lazy="dynamic")
    observations = relationship("IncidentObservation", back_populates="incident", lazy="dynamic")
    status_history = relationship("IncidentStatusHistory", back_populates="incident", lazy="dynamic")
    assignments = relationship("IncidentAssignment", back_populates="incident", lazy="dynamic")

    __table_args__ = (
        CheckConstraint(
            "severity IN ('minor','moderate','severe','critical')",
            name="ck_incident_severity"
        ),
        CheckConstraint(
            "status IN ('reported','acknowledged','scheduled','in_progress','repaired','verified','closed')",
            name="ck_incident_status"
        ),
        CheckConstraint(
            "category IN ('pothole','road_damage','bridge_damage','garbage','water_leakage','drainage','broken_streetlight','other')",
            name="ck_incident_category"
        ),
        Index("ix_incidents_v2_coords", "latitude", "longitude"),
        Index("ix_incidents_v2_status", "status"),
        Index("ix_incidents_v2_severity", "severity"),
        Index("ix_incidents_v2_category", "category"),
    )


# ─── Citizen Reports ─────────────────────────────────────────────────

class CitizenReport(Base):
    __tablename__ = "citizen_reports_v2"

    id = Column(String(36), primary_key=True, default=_uuid)
    citizen_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    report_reference = Column(String(20), unique=True, nullable=True)
    description = Column(Text, nullable=True)
    original_language = Column(String(5), nullable=False, default="en")
    translated_description = Column(Text, nullable=True)
    submission_channel = Column(String(30), nullable=False, default="web")
    status = Column(String(20), nullable=False, default="submitted")

    submitted_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    citizen = relationship("User", back_populates="reports")
    items = relationship("ReportItem", back_populates="report", cascade="all, delete-orphan")
    evidence_links = relationship("ReportEvidence", back_populates="report", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "submission_channel IN ('mobile_app','web','vehicle_telematics','manual_official','phone_call')",
            name="ck_report_channel"
        ),
        CheckConstraint(
            "status IN ('submitted','under_review','linked','rejected','withdrawn')",
            name="ck_report_status"
        ),
        Index("ix_reports_v2_citizen", "citizen_id"),
        Index("ix_reports_v2_status", "status"),
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
    storage_key = Column(Text, nullable=True)
    media_type = Column(String(50), nullable=True)
    file_size_bytes = Column(Integer, nullable=True, default=0)
    original_filename = Column(String(255), nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    report_links = relationship("ReportEvidence", back_populates="evidence_asset")
    detection_runs = relationship("DetectionRun", back_populates="evidence_asset", lazy="dynamic")

    __table_args__ = (
        Index("ix_evidence_sha256_v2", "content_sha256"),
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
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    evidence_asset = relationship("EvidenceAsset", back_populates="detection_runs")
    detections = relationship("Detection", back_populates="detection_run", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "processing_status IN ('pending','running','completed','failed')",
            name="ck_detection_run_status"
        ),
    )


# ─── Detections ───────────────────────────────────────────────────────

class Detection(Base):
    __tablename__ = "detections_v3"

    id = Column(String(36), primary_key=True, default=_uuid)
    detection_run_id = Column(String(36), ForeignKey("detection_runs.id", ondelete="CASCADE"), nullable=False)
    detected_category = Column(String(50), nullable=False, default="pothole")
    confidence_score = Column(Float, nullable=False, default=0.0)
    bbox_x = Column(Integer, nullable=True, default=0)
    bbox_y = Column(Integer, nullable=True, default=0)
    bbox_w = Column(Integer, nullable=True, default=0)
    bbox_h = Column(Integer, nullable=True, default=0)
    est_depth_cm = Column(Float, nullable=True)
    severity = Column(String(10), nullable=True)
    model_version = Column(String(50), nullable=True)
    review_status = Column(String(20), nullable=False, default="unreviewed")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    detection_run = relationship("DetectionRun", back_populates="detections")

    __table_args__ = (
        CheckConstraint("confidence_score BETWEEN 0.0 AND 1.0", name="ck_detection_confidence"),
        CheckConstraint(
            "review_status IN ('unreviewed','confirmed','rejected','uncertain')",
            name="ck_detection_review_status"
        ),
        Index("ix_detections_v3_run", "detection_run_id"),
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


# ─── Match Decisions ─────────────────────────────────────────────────

class MatchDecision(Base):
    __tablename__ = "match_decisions_v2"

    id = Column(String(36), primary_key=True, default=_uuid)
    report_item_id = Column(String(36), ForeignKey("report_items.id", ondelete="CASCADE"), nullable=False)
    candidate_incident_id = Column(String(36), ForeignKey("incidents_v2.id", ondelete="SET NULL"), nullable=True)
    visual_similarity_score = Column(Float, nullable=True)
    geographic_distance_m = Column(Float, nullable=True)
    category_similarity_score = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    decision = Column(String(30), nullable=False)
    decision_reason = Column(Text, nullable=True)
    reviewed_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    report_item = relationship("ReportItem", back_populates="match_decisions")

    __table_args__ = (
        CheckConstraint(
            "decision IN ('LIKELY_EXISTING_INCIDENT','NEEDS_HUMAN_CONFIRMATION','NEW_INCIDENT','INSUFFICIENT_EVIDENCE')",
            name="ck_match_decision"
        ),
        Index("ix_match_decisions_v2_item", "report_item_id"),
        Index("ix_match_decisions_v2_incident", "candidate_incident_id"),
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
    description = Column(Text, nullable=True)
    contact_email = Column(String(320), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    assignments = relationship("IncidentAssignment", back_populates="department", lazy="dynamic")


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
