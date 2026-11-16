"""
CivicLens Inspection and Resolution Workflow Service
====================================================
Manages on-site officer inspections, work progression milestones, hold reasons,
mandatory before/after photographic resolution pairing, and citizen synchronization.
"""

import os
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import (
    Incident, InspectionRecord, WorkProgressUpdate, ResolutionRecord,
    EvidenceAsset, CitizenReport, ReportItem, ReportEvidence, CitizenVisibleUpdate,
    User, AuditLog
)
from backend.services.incident_state_machine_service import IncidentStatus, IncidentStateMachineService
from backend.errors import ValidationError, NotFoundError, CivicLensError


VALID_CONDITION_RATINGS = {"minor", "moderate", "severe", "critical"}
ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp"
}
MAX_FILE_SIZE_BYTES = 16 * 1024 * 1024


class InspectionResolutionService:
    """Handles field inspection logs, progress updates, and verified repair resolutions."""

    def __init__(self, session_factory=None, upload_dir: Optional[str] = None):
        self._custom_session_factory = session_factory
        self.state_machine = IncidentStateMachineService(session_factory=self._session_factory)
        self._upload_dir = Path(upload_dir or "uploads/evidence").resolve()
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def upload_evidence_asset(
        self,
        raw_bytes: bytes,
        orig_name: str,
        mime: str = "image/jpeg"
    ) -> Dict[str, Any]:
        """Validates and persists photographic evidence from field inspections or repairs."""
        if not raw_bytes:
            raise ValidationError("Evidence file content cannot be empty.")

        if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
            raise ValidationError(f"File '{orig_name}' exceeds maximum allowed size of 16MB.")

        ext = ALLOWED_MIME_TYPES.get(mime.lower())
        if not ext:
            _, file_ext = os.path.splitext(orig_name.lower())
            if file_ext in (".jpg", ".jpeg"):
                ext = ".jpg"
                mime = "image/jpeg"
            elif file_ext == ".png":
                ext = ".png"
                mime = "image/png"
            elif file_ext == ".webp":
                ext = ".webp"
                mime = "image/webp"
            else:
                raise ValidationError(f"Unsupported media format '{mime}'. Allowed: JPEG, PNG, WebP.")

        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        db: Session = self._session_factory()
        try:
            existing_asset = db.query(EvidenceAsset).filter_by(content_sha256=sha256).first()
            if existing_asset:
                return {
                    "asset_id": existing_asset.id,
                    "media_type": existing_asset.media_type,
                    "sha256": existing_asset.content_sha256,
                    "file_size": existing_asset.file_size_bytes
                }

            safe_filename = f"{sha256[:16]}_{uuid.uuid4().hex[:8]}{ext}"
            target_path = self._upload_dir / safe_filename
            with open(target_path, "wb") as f:
                f.write(raw_bytes)

            asset = EvidenceAsset(
                id=str(uuid.uuid4()),
                content_sha256=sha256,
                storage_key=str(target_path),
                media_type=mime,
                file_size_bytes=len(raw_bytes),
                original_filename=Path(orig_name).name[:250],
            )
            db.add(asset)
            db.commit()

            return {
                "asset_id": asset.id,
                "media_type": asset.media_type,
                "sha256": asset.content_sha256,
                "file_size": asset.file_size_bytes
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def record_inspection(
        self,
        incident_id: str,
        officer_id: str,
        findings: str,
        confirmed_defect_type: str,
        condition_rating: str = "moderate",
        evidence_asset_id: Optional[str] = None,
        next_action: str = "schedule_repair"
    ) -> Dict[str, Any]:
        """Records an official municipal on-site inspection."""
        if not findings or len(findings.strip()) < 5:
            raise ValidationError("Detailed inspection findings (at least 5 characters) are required.")

        if condition_rating not in VALID_CONDITION_RATINGS:
            raise ValidationError(f"Invalid condition rating '{condition_rating}'. Allowed: {sorted(VALID_CONDITION_RATINGS)}")

        if not confirmed_defect_type or len(confirmed_defect_type.strip()) < 2:
            raise ValidationError("Confirmed defect type is required.")

        db: Session = self._session_factory()
        try:
            incident = db.query(Incident).filter_by(id=incident_id).first()
            if not incident:
                raise NotFoundError(f"Incident '{incident_id}' not found.")

            if evidence_asset_id:
                asset = db.query(EvidenceAsset).filter_by(id=evidence_asset_id).first()
                if not asset:
                    raise NotFoundError(f"Evidence asset '{evidence_asset_id}' not found.")

            # Priority escalation if severe or critical
            if condition_rating == "critical":
                incident.priority = "critical"
            elif condition_rating == "severe" and incident.priority in {"low", "normal"}:
                incident.priority = "high"

            # Auto-verify if awaiting verification
            if incident.status in {IncidentStatus.NEW, IncidentStatus.AWAITING_VERIFICATION}:
                self.state_machine.transition_incident(
                    incident_id=incident.id,
                    new_status=IncidentStatus.VERIFIED,
                    actor_id=officer_id,
                    actor_role="municipal_officer",
                    reason=f"Verified during inspection: {condition_rating} {confirmed_defect_type}",
                    session=db
                )

            record = InspectionRecord(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                officer_id=officer_id,
                inspection_date=datetime.now(timezone.utc),
                findings=findings.strip(),
                confirmed_defect_type=confirmed_defect_type.strip(),
                condition_rating=condition_rating,
                evidence_asset_id=evidence_asset_id,
                next_action=next_action.strip() if next_action else "schedule_repair",
                created_at=datetime.now(timezone.utc)
            )
            db.add(record)

            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=officer_id,
                action="record_inspection",
                entity_type="incident",
                entity_id=incident.id,
                details=json.dumps({
                    "condition_rating": condition_rating,
                    "confirmed_defect_type": confirmed_defect_type,
                    "evidence_asset_id": evidence_asset_id,
                    "next_action": next_action
                }),
                created_at=datetime.now(timezone.utc)
            )
            db.add(audit)

            db.commit()
            return {
                "id": record.id,
                "incident_id": incident.id,
                "findings": record.findings,
                "confirmed_defect_type": record.confirmed_defect_type,
                "condition_rating": record.condition_rating,
                "next_action": record.next_action,
                "created_at": record.created_at.isoformat()
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def record_work_progress(
        self,
        incident_id: str,
        officer_id: str,
        stage: str,
        notes: Optional[str] = None,
        hold_reason: Optional[str] = None,
        estimated_completion: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Records a maintenance progress update, materials requisition, or work hold."""
        if not stage or len(stage.strip()) < 2:
            raise ValidationError("Work stage description is required.")
        stage = stage.strip()

        db: Session = self._session_factory()
        try:
            incident = db.query(Incident).filter_by(id=incident_id).first()
            if not incident:
                raise NotFoundError(f"Incident '{incident_id}' not found.")

            # Status transition if hold or progress
            if "hold" in stage.lower() or hold_reason:
                if not hold_reason or len(hold_reason.strip()) < 5:
                    raise ValidationError("A clear hold reason (at least 5 characters) is mandatory when placing work on hold.")
                if incident.status != IncidentStatus.ON_HOLD:
                    self.state_machine.transition_incident(
                        incident_id=incident.id,
                        new_status=IncidentStatus.ON_HOLD,
                        actor_id=officer_id,
                        actor_role="municipal_officer",
                        reason=f"Work placed on hold: {hold_reason.strip()}",
                        session=db
                    )
            elif incident.status in {IncidentStatus.ASSIGNED, IncidentStatus.ON_HOLD}:
                self.state_machine.transition_incident(
                    incident_id=incident.id,
                    new_status=IncidentStatus.IN_PROGRESS,
                    actor_id=officer_id,
                    actor_role="municipal_officer",
                    reason=f"Work resumed / commenced: {stage}",
                    session=db
                )

            update = WorkProgressUpdate(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                officer_id=officer_id,
                stage=stage,
                notes=notes.strip() if notes else None,
                hold_reason=hold_reason.strip() if hold_reason else None,
                estimated_completion=estimated_completion,
                created_at=datetime.now(timezone.utc)
            )
            db.add(update)

            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=officer_id,
                action="record_work_progress",
                entity_type="incident",
                entity_id=incident.id,
                details=json.dumps({
                    "stage": stage,
                    "notes": notes,
                    "hold_reason": hold_reason
                }),
                created_at=datetime.now(timezone.utc)
            )
            db.add(audit)

            db.commit()
            return {
                "id": update.id,
                "incident_id": incident.id,
                "stage": update.stage,
                "notes": update.notes,
                "hold_reason": update.hold_reason,
                "created_at": update.created_at.isoformat()
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def record_resolution(
        self,
        incident_id: str,
        resolved_by: str,
        resolution_notes: str,
        after_evidence_id: str,
        before_evidence_id: Optional[str] = None,
        approved_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records the verified resolution of an incident with mandatory photographic proof.
        Pairs before-evidence and after-evidence and marks linked citizen reports as resolved.
        """
        if not resolution_notes or len(resolution_notes.strip()) < 10:
            raise ValidationError("Detailed resolution notes (at least 10 characters) describing the repair work are required.")

        if not after_evidence_id:
            raise ValidationError("Mandatory 'after' photographic evidence is required to prove defect resolution.")

        db: Session = self._session_factory()
        try:
            incident = db.query(Incident).filter_by(id=incident_id).first()
            if not incident:
                raise NotFoundError(f"Incident '{incident_id}' not found.")

            after_asset = db.query(EvidenceAsset).filter_by(id=after_evidence_id).first()
            if not after_asset:
                raise NotFoundError(f"After evidence asset '{after_evidence_id}' not found.")

            # Auto-discover before evidence if not explicitly passed
            if not before_evidence_id:
                # Find an evidence asset from linked reports
                rep_evidence = db.query(ReportEvidence).join(
                    CitizenReport, ReportEvidence.report_id == CitizenReport.id
                ).join(
                    ReportItem, ReportItem.report_id == CitizenReport.id
                ).filter(
                    ReportItem.incident_id == incident.id
                ).first()
                if rep_evidence:
                    before_evidence_id = rep_evidence.evidence_id
                else:
                    # Fallback to any inspection record asset
                    insp = db.query(InspectionRecord).filter(
                        InspectionRecord.incident_id == incident.id,
                        InspectionRecord.evidence_asset_id != None
                    ).first()
                    if insp:
                        before_evidence_id = insp.evidence_asset_id

            if before_evidence_id:
                before_asset = db.query(EvidenceAsset).filter_by(id=before_evidence_id).first()
                if not before_asset:
                    before_evidence_id = None

            # Check if resolution record already exists
            existing_res = db.query(ResolutionRecord).filter_by(incident_id=incident.id).first()
            if existing_res:
                existing_res.resolved_by = resolved_by
                existing_res.resolution_notes = resolution_notes.strip()
                existing_res.after_evidence_id = after_evidence_id
                existing_res.before_evidence_id = before_evidence_id
                existing_res.resolved_at = datetime.now(timezone.utc)
                if approved_by:
                    existing_res.approved_by = approved_by
                    existing_res.approved_at = datetime.now(timezone.utc)
                res_record = existing_res
            else:
                res_record = ResolutionRecord(
                    id=str(uuid.uuid4()),
                    incident_id=incident.id,
                    resolved_by=resolved_by,
                    resolution_notes=resolution_notes.strip(),
                    before_evidence_id=before_evidence_id,
                    after_evidence_id=after_evidence_id,
                    resolved_at=datetime.now(timezone.utc),
                    approved_by=approved_by,
                    approved_at=datetime.now(timezone.utc) if approved_by else None,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(res_record)

            # Move status to resolved via state machine
            self.state_machine.transition_incident(
                incident_id=incident.id,
                new_status=IncidentStatus.RESOLVED,
                actor_id=resolved_by,
                actor_role="municipal_officer",
                reason=resolution_notes.strip(),
                session=db
            )

            audit = AuditLog(
                id=str(uuid.uuid4()),
                actor_id=resolved_by,
                action="record_resolution",
                entity_type="incident",
                entity_id=incident.id,
                details=json.dumps({
                    "resolution_notes": resolution_notes,
                    "before_evidence_id": before_evidence_id,
                    "after_evidence_id": after_evidence_id,
                    "approved_by": approved_by
                }),
                created_at=datetime.now(timezone.utc)
            )
            db.add(audit)

            db.commit()
            return {
                "id": res_record.id,
                "incident_id": incident.id,
                "resolution_notes": res_record.resolution_notes,
                "before_evidence_id": res_record.before_evidence_id,
                "after_evidence_id": res_record.after_evidence_id,
                "resolved_at": res_record.resolved_at.isoformat()
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_incident_lifecycle_details(self, incident_id: str) -> Dict[str, Any]:
        """Returns comprehensive history of inspections, progress milestones, and resolution."""
        db: Session = self._session_factory()
        try:
            inspections = db.query(InspectionRecord).filter_by(
                incident_id=incident_id
            ).order_by(InspectionRecord.inspection_date.asc()).all()

            progress_updates = db.query(WorkProgressUpdate).filter_by(
                incident_id=incident_id
            ).order_by(WorkProgressUpdate.created_at.asc()).all()

            resolution = db.query(ResolutionRecord).filter_by(
                incident_id=incident_id
            ).first()

            return {
                "incident_id": incident_id,
                "inspections": [{
                    "id": i.id,
                    "officer_id": i.officer_id,
                    "inspection_date": i.inspection_date.isoformat(),
                    "findings": i.findings,
                    "confirmed_defect_type": i.confirmed_defect_type,
                    "condition_rating": i.condition_rating,
                    "evidence_asset_id": i.evidence_asset_id,
                    "next_action": i.next_action
                } for i in inspections],
                "progress_updates": [{
                    "id": p.id,
                    "officer_id": p.officer_id,
                    "stage": p.stage,
                    "notes": p.notes,
                    "hold_reason": p.hold_reason,
                    "estimated_completion": p.estimated_completion.isoformat() if p.estimated_completion else None,
                    "created_at": p.created_at.isoformat()
                } for p in progress_updates],
                "resolution": {
                    "id": resolution.id,
                    "resolved_by": resolution.resolved_by,
                    "resolution_notes": resolution.resolution_notes,
                    "before_evidence_id": resolution.before_evidence_id,
                    "after_evidence_id": resolution.after_evidence_id,
                    "resolved_at": resolution.resolved_at.isoformat(),
                    "approved_by": resolution.approved_by
                } if resolution else None
            }
        finally:
            db.close()
