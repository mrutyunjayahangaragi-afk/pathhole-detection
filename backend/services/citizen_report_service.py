"""
CivicLens Citizen Grievance Reporting Service
=============================================

Handles report submission, multi-file evidence attachment, location tagging,
idempotency, and scoped report querying for citizens.
"""

import os
import re
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from backend.db.engine import get_session_factory
from backend.db.session import transactional_session
from backend.db.models import (
    CitizenReport, ReportItem, EvidenceAsset, ReportEvidence,
    IncidentObservation, User
)
from backend.errors import ValidationError, NotFoundError, CivicLensError

ALLOWED_CATEGORIES = {
    "pothole", "road_damage", "bridge_damage", "garbage",
    "water_leakage", "drainage", "broken_streetlight", "other"
}

ALLOWED_SEVERITIES = {"minor", "moderate", "severe", "critical"}

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
}

MAX_FILE_SIZE_BYTES = 16 * 1024 * 1024  # 16 MB


class CitizenReportService:
    """Manages citizen complaints, multi-evidence uploads, and report timelines."""

    def __init__(self, session_factory=None, upload_dir: Optional[str] = None):
        self._custom_session_factory = session_factory
        self._upload_dir = Path(upload_dir or "uploads/evidence").resolve()
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def _generate_report_reference(self) -> str:
        """Generates a human-readable unique reference: CR-YYYYMM-XXXXX."""
        now = datetime.now(timezone.utc)
        ym = now.strftime("%Y%m")
        suffix = uuid.uuid4().hex[:5].upper()
        return f"CR-{ym}-{suffix}"

    def create_report(
        self,
        citizen_id: str,
        title: str,
        description: str,
        category: str,
        severity: str = "minor",
        latitude: float = 0.0,
        longitude: float = 0.0,
        location_accuracy_m: Optional[float] = None,
        is_manual_location: bool = False,
        address: Optional[str] = None,
        original_language: str = "en",
        idempotency_key: Optional[str] = None,
        evidence_files: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a citizen grievance report with associated report item and evidence assets.
        Guarantees atomicity via single database transaction.
        """
        # 1. Validation
        if not citizen_id:
            raise ValidationError("Authenticated citizen ID is required")

        if not title or len(title.strip()) < 3:
            raise ValidationError("Complaint title is required (at least 3 characters)")
        title_clean = title.strip()

        if not description or len(description.strip()) < 5:
            raise ValidationError("Complaint description is required (at least 5 characters)")
        desc_clean = description.strip()

        cat_clean = category.strip().lower() if category else "other"
        if cat_clean not in ALLOWED_CATEGORIES:
            raise ValidationError(
                f"Invalid category '{cat_clean}'. Allowed: {', '.join(sorted(ALLOWED_CATEGORIES))}"
            )

        sev_clean = severity.strip().lower() if severity else "minor"
        if sev_clean not in ALLOWED_SEVERITIES:
            raise ValidationError(
                f"Invalid severity '{sev_clean}'. Allowed: {', '.join(sorted(ALLOWED_SEVERITIES))}"
            )

        try:
            lat = float(latitude)
            lon = float(longitude)
        except (ValueError, TypeError):
            raise ValidationError("Latitude and longitude must be valid floating-point numbers")

        if not (-90.0 <= lat <= 90.0):
            raise ValidationError(f"Latitude {lat} out of valid range [-90, 90]")
        if not (-180.0 <= lon <= 180.0):
            raise ValidationError(f"Longitude {lon} out of valid range [-180, 180]")

        lang_clean = original_language.strip().lower() if original_language else "en"
        if lang_clean not in ("en", "kn"):
            lang_clean = "en"

        db = self._session_factory()
        created_file_paths = []

        try:
            # 2. Idempotency Check
            if idempotency_key:
                existing = db.query(CitizenReport).filter_by(idempotency_key=idempotency_key).first()
                if existing:
                    return self._serialize_report(existing, db)

            # 3. Create Report Record
            report_ref = self._generate_report_reference()
            report = CitizenReport(
                id=str(uuid.uuid4()),
                citizen_id=citizen_id,
                report_reference=report_ref,
                title=title_clean,
                description=desc_clean,
                reported_severity=sev_clean,
                latitude=lat,
                longitude=lon,
                location_accuracy_m=location_accuracy_m,
                is_manual_location=bool(is_manual_location),
                address=address.strip() if address else None,
                original_language=lang_clean,
                submission_channel="web",
                status="submitted",
                idempotency_key=idempotency_key if idempotency_key else None,
            )
            db.add(report)

            # 4. Create primary ReportItem
            item = ReportItem(
                id=str(uuid.uuid4()),
                report_id=report.id,
                category=cat_clean,
                description=desc_clean,
                status="pending",
            )
            db.add(item)

            # 5. Process and Store Evidence Files
            if evidence_files:
                for file_info in evidence_files:
                    raw_bytes = file_info.get("content_bytes", b"")
                    orig_name = file_info.get("filename", "evidence.jpg")
                    mime = file_info.get("mime_type", "image/jpeg").lower()

                    if not raw_bytes:
                        continue

                    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
                        raise ValidationError(
                            f"File '{orig_name}' exceeds maximum allowed size of 16MB"
                        )

                    # Validate extension and mime
                    ext = ALLOWED_MIME_TYPES.get(mime)
                    if not ext:
                        # Fallback extension check
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
                        elif file_ext == ".mp4":
                            ext = ".mp4"
                            mime = "video/mp4"
                        else:
                            raise ValidationError(
                                f"Unsupported media format '{mime}' for file '{orig_name}'. Allowed: JPEG, PNG, WebP, MP4."
                            )

                    # Content SHA-256 for deduplication
                    sha256 = hashlib.sha256(raw_bytes).hexdigest()

                    # Check if asset already exists in database
                    existing_asset = db.query(EvidenceAsset).filter_by(content_sha256=sha256).first()
                    if existing_asset:
                        asset = existing_asset
                    else:
                        safe_filename = f"{sha256[:16]}_{uuid.uuid4().hex[:8]}{ext}"
                        target_path = self._upload_dir / safe_filename
                        with open(target_path, "wb") as f:
                            f.write(raw_bytes)
                        created_file_paths.append(target_path)

                        asset = EvidenceAsset(
                            id=str(uuid.uuid4()),
                            content_sha256=sha256,
                            storage_key=str(target_path),
                            media_type=mime,
                            file_size_bytes=len(raw_bytes),
                            original_filename=Path(orig_name).name[:250],
                        )
                        db.add(asset)

                    # Create junction link
                    rep_evidence = ReportEvidence(
                        id=str(uuid.uuid4()),
                        report_id=report.id,
                        report_item_id=item.id,
                        evidence_asset_id=asset.id,
                        submitted_latitude=lat,
                        submitted_longitude=lon,
                        gps_source="manual" if is_manual_location else "browser_gps",
                        gps_accuracy_m=location_accuracy_m,
                    )
                    db.add(rep_evidence)

            db.commit()
            return self._serialize_report(report, db)

        except Exception as e:
            db.rollback()
            # Clean up any newly created disk files on rollback
            for p in created_file_paths:
                try:
                    if p.exists():
                        p.unlink()
                except OSError:
                    pass
            raise
        finally:
            db.close()

    def list_citizen_reports(
        self,
        citizen_id: str,
        status: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 10,
    ) -> Dict[str, Any]:
        """Lists reports owned by the authenticated citizen with filtering and pagination."""
        db = self._session_factory()
        try:
            query = db.query(CitizenReport).filter_by(citizen_id=citizen_id)

            if status and status.strip() != "all":
                query = query.filter(CitizenReport.status == status.strip().lower())

            if category and category.strip() != "all":
                query = query.join(ReportItem).filter(ReportItem.category == category.strip().lower())

            if search and search.strip():
                term = f"%{search.strip().lower()}%"
                query = query.filter(
                    (CitizenReport.title.ilike(term)) |
                    (CitizenReport.description.ilike(term)) |
                    (CitizenReport.report_reference.ilike(term)) |
                    (CitizenReport.address.ilike(term))
                )

            total = query.count()
            page = max(1, page)
            per_page = max(1, min(per_page, 50))
            offset = (page - 1) * per_page

            reports = (
                query.order_by(CitizenReport.created_at.desc())
                .offset(offset)
                .limit(per_page)
                .all()
            )

            serialized = [self._serialize_report(r, db) for r in reports]

            return {
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page if total > 0 else 1,
                "total_pages": (total + per_page - 1) // per_page if total > 0 else 1,
                "items": serialized,
                "reports": serialized,
            }
        finally:
            db.close()

    def get_citizen_report(self, report_id: str, citizen_id: str) -> Dict[str, Any]:
        """
        Retrieves a single report owned by the citizen (strict IDOR check).
        Raises NotFoundError if not found or unauthorized.
        """
        db = self._session_factory()
        try:
            report = db.query(CitizenReport).filter_by(id=report_id, citizen_id=citizen_id).first()
            if not report:
                # Also check by report_reference for flexibility
                report = db.query(CitizenReport).filter_by(report_reference=report_id, citizen_id=citizen_id).first()

            if not report:
                raise NotFoundError("Report not found or access denied")

            return self._serialize_report(report, db, include_evidence=True)
        finally:
            db.close()

    def get_evidence_file(self, asset_id: str, requesting_user_id: str, is_admin_or_officer: bool = False) -> Tuple[Path, str]:
        """
        Verifies permission and returns (file_path, mime_type) for an evidence asset.
        """
        db = self._session_factory()
        try:
            asset = db.query(EvidenceAsset).filter_by(id=asset_id).first()
            if not asset or not asset.storage_key:
                raise NotFoundError("Evidence asset not found")

            # Authorization check: is user an admin/officer, or the citizen who uploaded it?
            if not is_admin_or_officer:
                # Find associated citizen report
                link = (
                    db.query(ReportEvidence)
                    .join(CitizenReport, ReportEvidence.report_id == CitizenReport.id)
                    .filter(
                        ReportEvidence.evidence_asset_id == asset_id,
                        CitizenReport.citizen_id == requesting_user_id,
                    )
                    .first()
                )
                if not link:
                    raise NotFoundError("Evidence asset not found or access denied")

            file_path = Path(asset.storage_key)
            if not file_path.exists():
                raise NotFoundError("Evidence file missing from disk storage")

            return file_path, asset.media_type or "application/octet-stream"
        finally:
            db.close()

    def _serialize_report(self, r: CitizenReport, db, include_evidence: bool = False) -> Dict[str, Any]:
        """Helper to serialize a CitizenReport ORM entity into a clean dict."""
        items = db.query(ReportItem).filter_by(report_id=r.id).all()
        categories = [item.category for item in items]
        category = categories[0] if categories else "pothole"

        data = {
            "id": r.id,
            "report_reference": r.report_reference,
            "reference_code": r.report_reference,
            "title": r.title or f"{category.capitalize()} Report",
            "description": r.description,
            "category": category,
            "severity": r.reported_severity or "minor",
            "reported_severity": r.reported_severity or "minor",
            "status": r.status,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "location_accuracy_m": r.location_accuracy_m,
            "is_manual_location": r.is_manual_location,
            "address": r.address,
            "original_language": r.original_language,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "items": [
                {
                    "id": item.id,
                    "category": item.category,
                    "description": item.description,
                    "status": item.status,
                }
                for item in items
            ],
        }

        # Query evidence count & details
        evidence_links = db.query(ReportEvidence).filter_by(report_id=r.id).all()
        data["evidence_count"] = len(evidence_links)

        if include_evidence or len(evidence_links) > 0:
            evidence_list = []
            for link in evidence_links:
                asset = db.query(EvidenceAsset).filter_by(id=link.evidence_asset_id).first()
                if asset:
                    evidence_list.append({
                        "id": asset.id,
                        "original_filename": asset.original_filename,
                        "media_type": asset.media_type,
                        "file_size_bytes": asset.file_size_bytes,
                        "created_at": asset.created_at.isoformat() if asset.created_at else None,
                        "download_url": f"/api/v1/evidence/{asset.id}",
                    })
            data["evidence"] = evidence_list

        return data
