"""
Visual Embedding Service
========================
Provides object-level feature embedding extraction and cosine similarity
computation for individual defect crops.

Supports multiple embedding providers via a pluggable Strategy pattern:
- MockEmbeddingProvider: Deterministic 128-dimensional unit vector provider for unit tests & CI/CD.
- LocalVisionEmbeddingProvider: Extensible adapter for local PyTorch / DINOv2 models with graceful fallback.
"""

from abc import ABC, abstractmethod
import math
from typing import List, Optional, Union
from PIL import Image
import hashlib
from backend.db.models import DetectionEmbedding


class BaseEmbeddingProvider(ABC):
    """Abstract interface for image crop embedding providers."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_version(self) -> str:
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def generate_embedding(self, image_crop: Image.Image) -> List[float]:
        """Extracts a normalized floating-point feature embedding vector."""
        pass


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """
    Deterministic unit-vector embedding provider based on spatial color histograms
    and regional brightness/contrast features.
    Guarantees deterministic, reproducible cosine similarities without torch/heavy dependencies.
    """

    def __init__(self, dimension: int = 128):
        self._dim = dimension

    @property
    def model_name(self) -> str:
        return "mock-dinov2-defect-embedder"

    @property
    def model_version(self) -> str:
        return "v1.0.0-mock"

    @property
    def dimension(self) -> int:
        return self._dim

    def is_available(self) -> bool:
        return True

    def generate_embedding(self, image_crop: Image.Image) -> List[float]:
        # Resize to 16x16 grayscale (256 pixels)
        thumb = image_crop.convert("L").resize((16, 16), Image.Resampling.BILINEAR)
        try:
            pixels = list(thumb.get_flattened_data())
        except AttributeError:
            pixels = list(thumb.getdata())

        mean_val = sum(pixels) / len(pixels)
        variance = sum((p - mean_val) ** 2 for p in pixels) / len(pixels)
        std_val = math.sqrt(variance)

        vector = []
        # Feature 1 & 2: Centered global brightness and contrast
        vector.append((mean_val - 128.0) / 128.0)
        vector.append(std_val / 64.0)

        # Features 3 to 18: 4x4 spatial quadrant mean differences relative to global mean
        for r in range(4):
            for c in range(4):
                cell_pixels = []
                for pr in range(r * 4, (r + 1) * 4):
                    for pc in range(c * 4, (c + 1) * 4):
                        cell_pixels.append(pixels[pr * 16 + pc])
                cell_mean = sum(cell_pixels) / len(cell_pixels)
                vector.append((cell_mean - mean_val) / 64.0)

        # Pad or pool to self._dim
        current_len = len(vector)
        if current_len < self._dim:
            # Add downsampled spatial frequency components
            step = len(pixels) / (self._dim - current_len)
            for i in range(self._dim - current_len):
                idx = min(len(pixels) - 1, int(i * step))
                vector.append((pixels[idx] - 128.0) / 128.0)
        else:
            vector = vector[:self._dim]

        # L2-normalize to unit length
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 1e-8:
            return [round(x / norm, 6) for x in vector]
        return [1.0 / math.sqrt(self._dim)] * self._dim


class LocalVisionEmbeddingProvider(BaseEmbeddingProvider):
    """
    Local DINOv2 / SigLIP visual feature provider.
    Fails safely if torch or model weights are missing.
    """

    def __init__(self, model_name: str = "dinov2_vits14", weights_path: Optional[str] = None):
        self._model_name = model_name
        self._weights_path = weights_path
        self._torch_available = False
        try:
            import torch  # noqa: F401
            self._torch_available = True
        except ImportError:
            self._torch_available = False

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return "v1.0.0"

    @property
    def dimension(self) -> int:
        return 384  # ViT-S dimension

    def is_available(self) -> bool:
        return self._torch_available and self._weights_path is not None

    def generate_embedding(self, image_crop: Image.Image) -> List[float]:
        if not self.is_available():
            raise RuntimeError(
                f"Embedding provider '{self.model_name}' is not available. "
                "Ensure torch is installed and weights are configured."
            )
        # Placeholder for full torch inference when configured
        return [0.0] * self.dimension


class VisualEmbeddingService:
    """Service orchestrating visual crop embedding generation and vector comparison."""

    def __init__(self, provider: Optional[BaseEmbeddingProvider] = None):
        self.provider = provider or MockEmbeddingProvider()

    def get_crop_embedding(self, image_crop: Image.Image) -> List[float]:
        """Generates embedding for a defect crop using the active provider."""
        return self.provider.generate_embedding(image_crop)

    @staticmethod
    def cosine_similarity(vec1: Optional[List[float]], vec2: Optional[List[float]]) -> float:
        """
        Calculates cosine similarity between two feature vectors:
        CosineSim(u, v) = (u . v) / (||u|| * ||v||)
        Bounded to [0.0, 1.0].
        """
        if not vec1 or not vec2:
            return 0.0

        if len(vec1) != len(vec2):
            return 0.0

        dot = 0.0
        norm1 = 0.0
        norm2 = 0.0

        for a, b in zip(vec1, vec2):
            dot += a * b
            norm1 += a * a
            norm2 += b * b

        if norm1 <= 1e-12 or norm2 <= 1e-12:
            return 0.0

        sim = dot / (math.sqrt(norm1) * math.sqrt(norm2))
        return max(0.0, min(1.0, round(sim, 4)))
