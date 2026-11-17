"""
CivicLens Showcase Service
==========================
Business logic for managing and serving the CivicLens Impact Showcase:
- Public safe media serialization (no citizen PII, no raw private GPS)
- Municipal media uploads with SHA-256 and MIME validation
- Curation, moderation, and publication workflows
"""

import os
import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

from backend.database.session import get_db_session
from backend.database.repositories.showcase_repository import ShowcaseRepository
from backend.db.models import HomepageShowcaseItem, EvidenceAsset, Incident, User, ResolutionRecord
from backend.services.storage_service import StorageService

ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_MIMES = {"video/mp4", "video/webm"}
MAX_SHOWCASE_FILE_SIZE = 16 * 1024 * 1024  # 16 MB


class ShowcaseService:
    def __init__(self):
        self.storage_service = StorageService()

    def get_public_showcase(
        self,
        category: Optional[str] = None,
        before_after_type: Optional[str] = None,
        featured_only: bool = False,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Returns approved & published showcase items for public display.
        Guarantees ZERO citizen PII, raw GPS coordinates, or confidential notes.
        """
        session = get_db_session()
        try:
            repo = ShowcaseRepository(session)
            items = repo.get_public_showcase_items(
                category=category,
                before_after_type=before_after_type,
                featured_only=featured_only,
                limit=limit,
            )
            result = []
            for item in items:
                inc_ref = None
                inc_status = "verified"
                if item.incident:
                    inc_ref = item.incident.incident_reference
                    inc_status = item.incident.status or "verified"

                result.append({
                    "id": item.id,
                    "title": item.title,
                    "description": item.description or "",
                    "category": item.category,
                    "media_type": item.media_type,
                    "media_url": f"/api/public/showcase/media/{item.id}",
                    "thumbnail_url": f"/api/public/showcase/media/{item.id}?thumb=1" if item.thumbnail_object_path else None,
                    "public_location_label": item.public_location_label,
                    "before_after_type": item.before_after_type,
                    "status": inc_status,
                    "incident_reference": inc_ref,
                    "incident_id": item.incident_id,
                    "incident_link": f"/frontend/public-incident.html?id={item.incident_id}" if item.incident_id else None,
                    "is_featured": item.is_featured,
                    "sort_order": item.sort_order,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                })
            return result
        finally:
            session.close()

    def get_media_file_info(self, item_id: str, as_thumb: bool = False) -> Tuple[Optional[str], Optional[str]]:
        """
        Retrieves local file path and MIME type for serving approved media.
        Returns (file_path, mime_type) or (None, None).
        """
        session = get_db_session()
        try:
            repo = ShowcaseRepository(session)
            item = repo.get_by_id(item_id)
            if not item:
                return None, None
            
            # Public endpoint only serves PUBLISHED and APPROVED media
            if item.publication_status != "PUBLISHED" or item.moderation_status != "APPROVED":
                return None, None

            object_path = item.thumbnail_object_path if (as_thumb and item.thumbnail_object_path) else item.storage_object_path
            mime_type = "video/mp4" if item.media_type == "VIDEO" and not as_thumb else "image/jpeg"

            # Check if object_path is local file
            if os.path.exists(object_path):
                return object_path, mime_type
            
            # Check relative to uploads directory
            candidate = os.path.join(os.getcwd(), object_path)
            if os.path.exists(candidate):
                return candidate, mime_type

            # Check evidence assets
            if item.evidence_asset and item.evidence_asset.storage_key:
                if os.path.exists(item.evidence_asset.storage_key):
                    return item.evidence_asset.storage_key, item.evidence_asset.media_type or mime_type

            return None, None
        finally:
            session.close()

    def upload_media_file(
        self,
        file: FileStorage,
        uploader_id: str,
        uploader_role: str,
    ) -> Dict[str, Any]:
        """
        Processes municipal upload, verifies MIME/size, generates SHA-256,
        and creates an EvidenceAsset record.
        """
        if not file or not file.filename:
            raise ValueError("No file provided")

        content = file.read()
        file.seek(0)
        file_size = len(content)

        if file_size > MAX_SHOWCASE_FILE_SIZE:
            raise ValueError(f"File size exceeds maximum allowed limit ({MAX_SHOWCASE_FILE_SIZE // (1024 * 1024)}MB)")

        # Determine MIME type
        mimetype = file.mimetype.lower() if file.mimetype else "application/octet-stream"
        ext = os.path.splitext(file.filename)[1].lower()

        if ext in (".jpg", ".jpeg"):
            mimetype = "image/jpeg"
        elif ext == ".png":
            mimetype = "image/png"
        elif ext == ".webp":
            mimetype = "image/webp"
        elif ext == ".mp4":
            mimetype = "video/mp4"
        elif ext == ".webm":
            mimetype = "video/webm"

        is_image = mimetype in ALLOWED_IMAGE_MIMES
        is_video = mimetype in ALLOWED_VIDEO_MIMES

        if not is_image and not is_video:
            raise ValueError(f"Unsupported file format '{ext}' (MIME: {mimetype}). Allowed: JPEG, PNG, WebP, MP4, WebM.")

        content_sha256 = hashlib.sha256(content).hexdigest()
        asset_id = str(uuid.uuid4())
        safe_name = f"showcase_{content_sha256[:16]}_{asset_id[:8]}{ext}"

        # Save to storage directory
        target_dir = os.path.join(os.getcwd(), "uploads", "evidence")
        os.makedirs(target_dir, exist_ok=True)
        local_path = os.path.join(target_dir, safe_name)

        with open(local_path, "wb") as f:
            f.write(content)

        session = get_db_session()
        try:
            # Check existing asset by hash
            asset = session.query(EvidenceAsset).filter_by(content_sha256=content_sha256).first()
            if not asset:
                asset = EvidenceAsset(
                    id=asset_id,
                    content_sha256=content_sha256,
                    storage_key=local_path,
                    media_type=mimetype,
                    file_size_bytes=file_size,
                    original_filename=file.filename[:250],
                    created_at=datetime.now(timezone.utc),
                )
                session.add(asset)
                session.commit()
            
            return {
                "asset_id": asset.id,
                "media_type": "VIDEO" if is_video else "IMAGE",
                "storage_key": local_path,
                "file_size": file_size,
                "content_hash": content_sha256,
                "original_filename": file.filename,
            }
        finally:
            session.close()

    def create_showcase_item(
        self,
        uploader_id: str,
        uploader_role: str,
        title: str,
        category: str,
        public_location_label: str,
        media_type: str,
        storage_object_path: str,
        evidence_asset_id: Optional[str] = None,
        incident_id: Optional[str] = None,
        description: Optional[str] = None,
        before_after_type: str = "STANDALONE",
        sort_order: int = 0,
        is_featured: bool = False,
    ) -> Dict[str, Any]:
        """Creates a new draft showcase item."""
        session = get_db_session()
        try:
            item_id = str(uuid.uuid4())
            item = HomepageShowcaseItem(
                id=item_id,
                evidence_asset_id=evidence_asset_id,
                incident_id=incident_id,
                uploader_id=uploader_id,
                uploader_role_snapshot=uploader_role,
                title=title,
                description=description,
                category=category or "pothole",
                media_type=media_type.upper(),
                storage_bucket="inspection-evidence",
                storage_object_path=storage_object_path,
                public_location_label=public_location_label,
                before_after_type=before_after_type.upper(),
                sort_order=sort_order,
                is_featured=is_featured,
                publication_status="DRAFT",
                moderation_status="PENDING",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(item)
            session.commit()
            return {"status": "success", "id": item.id}
        finally:
            session.close()

    def list_municipal_items(
        self,
        publication_status: Optional[str] = None,
        moderation_status: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        session = get_db_session()
        try:
            repo = ShowcaseRepository(session)
            items = repo.list_all_items(
                publication_status=publication_status,
                moderation_status=moderation_status,
                category=category,
            )
            res = []
            for it in items:
                res.append({
                    "id": it.id,
                    "title": it.title,
                    "description": it.description or "",
                    "category": it.category,
                    "media_type": it.media_type,
                    "media_url": f"/api/public/showcase/media/{it.id}",
                    "public_location_label": it.public_location_label,
                    "before_after_type": it.before_after_type,
                    "publication_status": it.publication_status,
                    "moderation_status": it.moderation_status,
                    "incident_id": it.incident_id,
                    "incident_ref": it.incident.incident_reference if it.incident else None,
                    "is_featured": it.is_featured,
                    "sort_order": it.sort_order,
                    "created_at": it.created_at.isoformat() if it.created_at else None,
                })
            return res
        finally:
            session.close()

    def update_item_status(
        self,
        item_id: str,
        action: str,
        user_id: str,
        user_role: str,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handles lifecycle transitions: submit, approve, reject, publish, unpublish."""
        session = get_db_session()
        try:
            repo = ShowcaseRepository(session)
            item = repo.get_by_id(item_id)
            if not item:
                return {"status": "error", "message": "Item not found", "code": 404}

            now = datetime.now(timezone.utc)

            if action == "submit":
                item.publication_status = "PENDING_REVIEW"
                item.moderation_status = "PENDING"
            elif action == "approve":
                if user_role not in ("dept_admin", "municipal_admin", "system_admin"):
                    return {"status": "error", "message": "Insufficient privileges to approve media", "code": 403}
                item.moderation_status = "APPROVED"
                item.approved_by = user_id
                item.approved_at = now
            elif action == "reject":
                if user_role not in ("dept_admin", "municipal_admin", "system_admin"):
                    return {"status": "error", "message": "Insufficient privileges to reject media", "code": 403}
                item.moderation_status = "REJECTED"
                item.publication_status = "REJECTED"
                item.rejection_reason = reason or "Does not meet civic publication guidelines"
            elif action == "publish":
                if user_role not in ("dept_admin", "municipal_admin", "system_admin", "municipal_officer"):
                    return {"status": "error", "message": "Insufficient privileges to publish media", "code": 403}
                if item.moderation_status != "APPROVED":
                    # Auto-approve if administrative officer
                    if user_role in ("dept_admin", "municipal_admin", "system_admin"):
                        item.moderation_status = "APPROVED"
                        item.approved_by = user_id
                        item.approved_at = now
                    else:
                        return {"status": "error", "message": "Item must be approved by an administrator before publishing", "code": 400}
                item.publication_status = "PUBLISHED"
            elif action == "unpublish":
                item.publication_status = "UNPUBLISHED"
            elif action == "archive":
                item.publication_status = "ARCHIVED"
            else:
                return {"status": "error", "message": f"Unknown action '{action}'", "code": 400}

            repo.update(item)
            return {"status": "success", "id": item.id, "publication_status": item.publication_status, "moderation_status": item.moderation_status}
        finally:
            session.close()
