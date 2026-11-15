"""
Image Preprocessing Service
===========================
Prepares validated PIL images for model inference:
- Scales image to model input size (default: 640x640) while maintaining aspect ratio
- Tracks letterboxing offsets and scaling ratios for coordinate inverse-mapping
- Converts PIL Image to numpy array (RGB and BGR formats)
"""

from dataclasses import dataclass
from typing import Tuple, Optional
from PIL import Image


@dataclass
class PreprocessedImage:
    """Preprocessed image and spatial mapping transformation parameters."""
    original_width: int
    original_height: int
    target_width: int
    target_height: int
    scale: float
    pad_x: int
    pad_y: int
    pil_image: Image.Image


class ImagePreprocessingService:
    """Handles letterbox scaling and array conversion for object detection models."""

    def __init__(self, target_size: int = 640):
        self.target_size = target_size

    def preprocess(self, img: Image.Image) -> PreprocessedImage:
        """
        Letterbox pads the image into (target_size, target_size) keeping aspect ratio.
        """
        orig_w, orig_h = img.size
        target = self.target_size

        scale = min(target / orig_w, target / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)

        resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)

        # Create padded background (114, 114, 114) — standard YOLO gray fill
        padded = Image.new("RGB", (target, target), (114, 114, 114))
        pad_x = (target - new_w) // 2
        pad_y = (target - new_h) // 2
        padded.paste(resized, (pad_x, pad_y))

        return PreprocessedImage(
            original_width=orig_w,
            original_height=orig_h,
            target_width=target,
            target_height=target,
            scale=scale,
            pad_x=pad_x,
            pad_y=pad_y,
            pil_image=padded,
        )

    def inverse_transform_box(
        self,
        box_xyxy: Tuple[float, float, float, float],
        preprocessed: PreprocessedImage,
    ) -> Tuple[int, int, int, int]:
        """
        Converts bounding box from preprocessed coordinates [x1, y1, x2, y2]
        back to original image coordinates [x, y, w, h] in integer pixels.
        """
        x1, y1, x2, y2 = box_xyxy

        # Subtract padding
        x1 = (x1 - preprocessed.pad_x) / preprocessed.scale
        y1 = (y1 - preprocessed.pad_y) / preprocessed.scale
        x2 = (x2 - preprocessed.pad_x) / preprocessed.scale
        y2 = (y2 - preprocessed.pad_y) / preprocessed.scale

        # Clamp to original image bounds
        x1 = max(0, min(x1, preprocessed.original_width))
        y1 = max(0, min(y1, preprocessed.original_height))
        x2 = max(0, min(x2, preprocessed.original_width))
        y2 = max(0, min(y2, preprocessed.original_height))

        x = int(round(x1))
        y = int(round(y1))
        w = int(round(max(0, x2 - x1)))
        h = int(round(max(0, y2 - y1)))

        return x, y, w, h
