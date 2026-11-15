"""
Evidence Asset Service
======================

Manages uploaded evidence files (photos, video), computing cryptographic
hashes (SHA-256) for exact deduplication, validating file formats safely,
and avoiding path-traversal vulnerabilities.
"""

import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple
import uuid

from backend.domain.models import EvidenceAsset
from backend.errors import ValidationError

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}


class EvidenceService:
    """Handles evidence asset validation, hashing, and storage abstraction."""

    def __init__(self, upload_dir: Optional[str] = None):
        self.upload_dir = Path(upload_dir or "uploads")
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Returns the hex-encoded SHA-256 digest of binary content."""
        return hashlib.sha256(data).hexdigest()

    def sanitize_filename(self, original_filename: str) -> str:
        """
        Generates a secure UUID-based filename while retaining safe extension,
        guaranteeing defense against directory traversal and malicious filenames.
        """
        clean_ext = Path(original_filename).suffix.lower()
        if clean_ext not in ALLOWED_IMAGE_EXTENSIONS:
            clean_ext = ".jpg"  # Default safe extension
        return f"{uuid.uuid4().hex}{clean_ext}"

    def create_asset_from_bytes(
        self, file_bytes: bytes, original_filename: str, report_id: str, mime_type: Optional[str] = None
    ) -> EvidenceAsset:
        """Validates and persists image bytes as an EvidenceAsset."""
        if not file_bytes:
            raise ValidationError("Evidence file content cannot be empty.")

        ext = Path(original_filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValidationError(
                f"Unsupported file format '{ext}'. Allowed: {sorted(ALLOWED_IMAGE_EXTENSIONS)}"
            )

        sha256 = self.compute_sha256(file_bytes)
        safe_filename = self.sanitize_filename(original_filename)
        dest_path = self.upload_dir / safe_filename

        with open(dest_path, "wb") as f:
            f.write(file_bytes)

        return EvidenceAsset(
            report_id=report_id,
            file_path=str(dest_path),
            sha256_hash=sha256,
            mime_type=mime_type or "image/jpeg",
            file_size_bytes=len(file_bytes),
        )
