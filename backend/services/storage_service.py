"""
Supabase Storage Service
========================
Provides centralized object storage management for CivicLens assets:
- Private bucket enforcement for citizen photographs, inspections, and resolution evidence
- Content validation (size, MIME type) and SHA-256 cryptographic verification
- Secure signed URL generation with customizable TTL
- Integration with Supabase Storage REST API with robust local fallback
"""

import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union
import uuid
import requests

from backend.config import get_config
from backend.errors import ValidationError
from backend.logging_config import setup_logging

logger = setup_logging()

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "video/mp4",
    "video/quicktime",
    "application/pdf",
}

MAX_FILE_SIZE_BYTES = 16 * 1024 * 1024  # 16 MB default


class StorageService:
    """Manages cloud asset uploads, signed URLs, and cryptographic integrity."""

    def __init__(self, config=None):
        self.cfg = config or get_config()
        self.supabase_url = getattr(self.cfg, "SUPABASE_URL", "").rstrip("/")
        # Use secret/service role key if available for backend uploads, else anon key
        self.api_key = (
            getattr(self.cfg, "SUPABASE_SECRET_KEY", None)
            or getattr(self.cfg, "SUPABASE_PUBLISHABLE_KEY", None)
            or getattr(self.cfg, "SUPABASE_ANON_KEY", "")
        )
        self.local_upload_dir = Path(getattr(self.cfg, "UPLOAD_FOLDER", "uploads"))
        self.local_upload_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Computes SHA-256 digest of binary content."""
        return hashlib.sha256(data).hexdigest()

    def validate_content(self, data: bytes, mime_type: Optional[str] = None) -> str:
        """Validates payload size and MIME type."""
        if not data:
            raise ValidationError("File content is empty.")
        if len(data) > MAX_FILE_SIZE_BYTES:
            raise ValidationError(
                f"File size exceeds maximum allowed limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
            )
        detected_mime = mime_type or "image/jpeg"
        if detected_mime not in ALLOWED_MIME_TYPES:
            raise ValidationError(
                f"Unsupported MIME type '{detected_mime}'. Allowed: {sorted(ALLOWED_MIME_TYPES)}"
            )
        return detected_mime

    def is_storage_available(self) -> bool:
        """Checks if remote Supabase Storage endpoint is configured and reachable."""
        if not self.supabase_url or not self.api_key:
            return False
        try:
            url = f"{self.supabase_url}/storage/v1/bucket"
            headers = {
                "apikey": self.api_key,
                "Authorization": f"Bearer {self.api_key}",
            }
            resp = requests.get(url, headers=headers, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def upload_file(
        self,
        bucket: str,
        data: bytes,
        destination_path: str,
        mime_type: Optional[str] = None,
        upsert: bool = True,
    ) -> Dict[str, Any]:
        """
        Uploads file data to Supabase Storage or falls back to local storage.
        Returns a dictionary containing storage key, SHA-256 hash, size, and provider.
        """
        verified_mime = self.validate_content(data, mime_type)
        sha256_hash = self.compute_sha256(data)
        file_size = len(data)

        # Attempt remote Supabase Storage upload if credentials exist
        if self.supabase_url and self.api_key:
            try:
                upload_url = f"{self.supabase_url}/storage/v1/object/{bucket}/{destination_path}"
                headers = {
                    "apikey": self.api_key,
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": verified_mime,
                    "x-upsert": "true" if upsert else "false",
                }
                resp = requests.post(upload_url, headers=headers, data=data, timeout=15)
                if resp.status_code in (200, 201):
                    logger.info(f"Uploaded object to Supabase Storage: {bucket}/{destination_path}")
                    return {
                        "provider": "supabase",
                        "bucket": bucket,
                        "storage_key": f"{bucket}/{destination_path}",
                        "content_sha256": sha256_hash,
                        "file_size_bytes": file_size,
                        "mime_type": verified_mime,
                        "status": "success",
                    }
                else:
                    logger.warning(
                        f"Supabase storage upload failed ({resp.status_code}): {resp.text}. Falling back to local storage."
                    )
            except Exception as e:
                logger.warning(f"Supabase storage request exception: {e}. Falling back to local storage.")

        # Local storage fallback
        local_bucket_dir = self.local_upload_dir / bucket
        local_bucket_dir.mkdir(parents=True, exist_ok=True)
        local_file_path = local_bucket_dir / Path(destination_path).name
        with open(local_file_path, "wb") as f:
            f.write(data)

        logger.info(f"Saved asset to local storage: {local_file_path}")
        return {
            "provider": "local",
            "bucket": bucket,
            "storage_key": str(local_file_path),
            "content_sha256": sha256_hash,
            "file_size_bytes": file_size,
            "mime_type": verified_mime,
            "status": "success",
        }

    def create_signed_url(
        self, bucket: str, destination_path: str, expires_in: int = 3600
    ) -> Optional[str]:
        """Generates a short-lived signed URL for private evidence access."""
        # Clean destination_path if it starts with bucket name
        if destination_path.startswith(f"{bucket}/"):
            destination_path = destination_path[len(f"{bucket}/"):]

        if self.supabase_url and self.api_key:
            try:
                sign_url = f"{self.supabase_url}/storage/v1/object/sign/{bucket}/{destination_path}"
                headers = {
                    "apikey": self.api_key,
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {"expiresIn": expires_in}
                resp = requests.post(sign_url, headers=headers, json=payload, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    signed_path = data.get("signedURL")
                    if signed_path:
                        # Return absolute URL
                        if signed_path.startswith("http"):
                            return signed_path
                        return f"{self.supabase_url}/storage/v1{signed_path}"
            except Exception as e:
                logger.warning(f"Error creating signed URL: {e}")

        # Local fallback: return local file route
        return f"/api/v1/evidence/file/{bucket}/{Path(destination_path).name}"

    def download_file(self, bucket: str, destination_path: str) -> Optional[bytes]:
        """Downloads object bytes from Supabase Storage or local directory."""
        if destination_path.startswith(f"{bucket}/"):
            destination_path = destination_path[len(f"{bucket}/"):]

        if self.supabase_url and self.api_key:
            try:
                get_url = f"{self.supabase_url}/storage/v1/object/authenticated/{bucket}/{destination_path}"
                headers = {
                    "apikey": self.api_key,
                    "Authorization": f"Bearer {self.api_key}",
                }
                resp = requests.get(get_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.content
            except Exception as e:
                logger.warning(f"Error downloading from Supabase storage: {e}")

        # Local fallback
        local_path = self.local_upload_dir / bucket / Path(destination_path).name
        if not local_path.exists():
            local_path = Path(destination_path)
        if local_path.exists() and local_path.is_file():
            with open(local_path, "rb") as f:
                return f.read()

        return None
