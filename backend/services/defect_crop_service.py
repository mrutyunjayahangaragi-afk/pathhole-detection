"""
Defect Crop Service
===================
Extracts high-fidelity physical defect crops from source evidence images
using Step 5 bounding boxes.

Ensures that multi-defect images (e.g. 3 distinct potholes) produce separate,
isolated crops for object-level visual feature extraction.
"""

from pathlib import Path
from typing import Optional, Tuple, Union
from PIL import Image
import io


class DefectCropService:
    """Extracts bounding box defect crops safely with coordinate bounds checking."""

    @staticmethod
    def crop_defect(
        image_input: Union[str, Path, Image.Image, bytes],
        bbox: Optional[Tuple[int, int, int, int]] = None,
        normalized_bbox: Optional[Tuple[float, float, float, float]] = None,
        padding_percent: float = 0.05,
    ) -> Image.Image:
        """
        Extracts cropped defect region from an image.

        Args:
            image_input: Source image (file path, bytes, or PIL Image).
            bbox: Absolute pixel coordinates (x, y, w, h).
            normalized_bbox: Normalized coordinates (xmin, ymin, xmax, ymax) in [0.0, 1.0].
            padding_percent: Context padding around defect border (default 5%).

        Returns:
            Cropped PIL Image in RGB mode.
        """
        if isinstance(image_input, (str, Path)):
            img = Image.open(str(image_input))
        elif isinstance(image_input, bytes):
            img = Image.open(io.BytesIO(image_input))
        elif isinstance(image_input, Image.Image):
            img = image_input
        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")

        img = img.convert("RGB")
        img_w, img_h = img.size

        if normalized_bbox is not None:
            n_xmin, n_ymin, n_xmax, n_ymax = normalized_bbox
            xmin = int(n_xmin * img_w)
            ymin = int(n_ymin * img_h)
            xmax = int(n_xmax * img_w)
            ymax = int(n_ymax * img_h)
        elif bbox is not None:
            x, y, w, h = bbox
            xmin = int(x)
            ymin = int(y)
            xmax = int(x + w)
            ymax = int(y + h)
        else:
            # Fallback: whole image if no bounding box provided
            return img

        # Apply padding
        pad_w = int((xmax - xmin) * padding_percent)
        pad_h = int((ymax - ymin) * padding_percent)

        xmin = max(0, xmin - pad_w)
        ymin = max(0, ymin - pad_h)
        xmax = min(img_w, xmax + pad_w)
        ymax = min(img_h, ymax + pad_h)

        # Minimum valid crop size guard
        if xmax <= xmin or ymax <= ymin:
            return img

        return img.crop((xmin, ymin, xmax, ymax))
