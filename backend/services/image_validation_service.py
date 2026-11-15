"""
Image Validation Service
========================
Validates image files prior to computer vision inference:
- File existence and storage accessibility
- Binary integrity and truncation checks
- MIME and image format verification (JPEG, PNG, WebP)
- Resolution sanity bounds (min 32x32, max 8192x8192) to avoid OOM / decompression bombs
- EXIF orientation extraction and normalization (exif_transpose)
"""

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

from PIL import Image, ImageOps, UnidentifiedImageError
from backend.errors import ValidationError

SUPPORTED_IMAGE_FORMATS = {"JPEG", "JPG", "PNG", "WEBP"}
MIN_DIMENSION = 32
MAX_DIMENSION = 8192


@dataclass
class ImageValidationResult:
    """Represents the output of image validation and preprocessing normalization."""
    is_valid: bool
    image: Optional[Image.Image] = None
    width: int = 0
    height: int = 0
    image_format: str = ""
    exif_transposed: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class ImageValidationService:
    """Handles image integrity, dimension limits, and orientation normalization."""

    def __init__(
        self,
        min_dimension: int = MIN_DIMENSION,
        max_dimension: int = MAX_DIMENSION,
    ):
        self.min_dimension = min_dimension
        self.max_dimension = max_dimension

    def validate_and_load(
        self,
        source: Union[str, Path, bytes, io.BytesIO],
    ) -> ImageValidationResult:
        """
        Validates the image from a file path or raw bytes, applies EXIF orientation,
        and returns a normalized PIL Image in RGB format.
        """
        raw_stream = None
        try:
            if isinstance(source, (str, Path)):
                file_path = Path(source)
                if not file_path.exists():
                    return ImageValidationResult(
                        is_valid=False,
                        error_code="FILE_NOT_FOUND",
                        error_message=f"Image file does not exist at '{file_path}'",
                    )
                if file_path.stat().st_size == 0:
                    return ImageValidationResult(
                        is_valid=False,
                        error_code="EMPTY_FILE",
                        error_message="Image file is 0 bytes",
                    )
                with open(file_path, "rb") as f:
                    content_bytes = f.read()
                raw_stream = io.BytesIO(content_bytes)
            elif isinstance(source, bytes):
                if len(source) == 0:
                    return ImageValidationResult(
                        is_valid=False,
                        error_code="EMPTY_FILE",
                        error_message="Image binary payload is empty",
                    )
                raw_stream = io.BytesIO(source)
            elif isinstance(source, io.BytesIO):
                raw_stream = source
            else:
                return ImageValidationResult(
                    is_valid=False,
                    error_code="INVALID_SOURCE_TYPE",
                    error_message=f"Unsupported image source type: {type(source)}",
                )

            # 1. Open with PIL and check format
            try:
                img = Image.open(raw_stream)
                img.verify()
            except (UnidentifiedImageError, OSError, SyntaxError) as e:
                return ImageValidationResult(
                    is_valid=False,
                    error_code="CORRUPTED_IMAGE",
                    error_message=f"Corrupted or invalid image binary: {e}",
                )

            # verify() leaves file pointer at end, reopen for raster reading
            raw_stream.seek(0)
            img = Image.open(raw_stream)

            fmt = (img.format or "").upper()
            if fmt not in SUPPORTED_IMAGE_FORMATS and fmt != "MPO":
                return ImageValidationResult(
                    is_valid=False,
                    error_code="UNSUPPORTED_FORMAT",
                    error_message=f"Unsupported image format '{fmt}'. Supported: {sorted(SUPPORTED_IMAGE_FORMATS)}",
                )

            # 2. Check dimensions
            w, h = img.size
            if w < self.min_dimension or h < self.min_dimension:
                return ImageValidationResult(
                    is_valid=False,
                    error_code="IMAGE_TOO_SMALL",
                    error_message=f"Image resolution {w}x{h} is below minimum allowed {self.min_dimension}x{self.min_dimension}",
                )

            if w > self.max_dimension or h > self.max_dimension:
                return ImageValidationResult(
                    is_valid=False,
                    error_code="IMAGE_TOO_LARGE",
                    error_message=f"Image resolution {w}x{h} exceeds maximum allowed {self.max_dimension}x{self.max_dimension}",
                )

            # 3. Handle EXIF orientation
            exif_applied = False
            try:
                transposed = ImageOps.exif_transpose(img)
                if transposed is not None:
                    if transposed.size != img.size or transposed.tobytes() != img.tobytes():
                        exif_applied = True
                    img = transposed
            except Exception:
                # If EXIF reading fails, continue with original raster
                pass

            # 4. Normalize to RGB color space
            if img.mode != "RGB":
                img = img.convert("RGB")

            final_w, final_h = img.size
            return ImageValidationResult(
                is_valid=True,
                image=img,
                width=final_w,
                height=final_h,
                image_format=fmt,
                exif_transposed=exif_applied,
            )

        except Exception as e:
            return ImageValidationResult(
                is_valid=False,
                error_code="IMAGE_PROCESSING_FAILED",
                error_message=f"Unexpected error during image validation: {e}",
            )
