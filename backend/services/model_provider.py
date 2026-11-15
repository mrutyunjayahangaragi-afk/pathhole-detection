"""
Model Provider Architecture (Strategy / Adapter Pattern)
=========================================================
Encapsulates machine learning defect detection models:
- Strategy / Adapter pattern enabling seamless substitution of models (YOLO, ONNX, PyTorch)
- Model metadata and version tracking
- Class filtering (only genuine supported categories: pothole, road_damage)
- Caching: loaded weights reside in memory rather than reloading on every frame
- Hardware device resolution (MPS for Apple Silicon, CUDA for NVIDIA, CPU default)
- Safe failure modes when weights file is not installed
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image

from backend.errors import CivicLensError


class ModelWeightsMissingError(CivicLensError):
    """Raised when inference is requested but model weights are missing or not installed."""
    status_code = 503
    error_code = "MODEL_WEIGHTS_MISSING"

    def __init__(self, weights_path: str, message: Optional[str] = None):
        msg = message or f"Model weights file not found at '{weights_path}'. Defect detection cannot proceed without trained weights."
        super().__init__(msg)
        self.weights_path = weights_path


class ModelNotAvailableError(CivicLensError):
    """Raised when machine learning dependencies or runtime engines are unavailable."""
    status_code = 503
    error_code = "MODEL_UNAVAILABLE"

    def __init__(self, reason: str):
        super().__init__(f"Detection model unavailable: {reason}")


@dataclass
class RawPrediction:
    """Individual raw defect candidate from model inference."""
    class_name: str
    confidence: float
    box_xyxy: Tuple[float, float, float, float]  # [x1, y1, x2, y2] in pixels
    est_depth_cm: Optional[float] = None


class BaseModelProvider(ABC):
    """Abstract Base Class for all defect detection model providers."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the model architecture."""
        pass

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Semantic version of the model checkpoint."""
        pass

    @property
    @abstractmethod
    def supported_classes(self) -> List[str]:
        """List of defect categories this model was actually trained to detect."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True only if weights file exists and runtime is ready."""
        pass

    @abstractmethod
    def load(self) -> None:
        """Loads weights into memory."""
        pass

    @abstractmethod
    def predict(self, image: Image.Image, conf_threshold: float = 0.40) -> List[RawPrediction]:
        """Runs object detection inference on the provided image."""
        pass

    def get_metadata(self) -> Dict[str, Any]:
        """Returns model audit information."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "supported_classes": self.supported_classes,
            "is_available": self.is_available(),
        }


class YoloModelProvider(BaseModelProvider):
    """
    Adapter for Ultralytics YOLOv8 object detection.
    Reuses model instance across calls; validates weight file existence.
    """

    SUPPORTED_CATEGORIES = ["pothole", "road_damage"]

    def __init__(
        self,
        weights_path: Optional[str] = None,
        model_name: str = "yolov8-pothole",
        model_version: str = "v1.0.0",
        device: Optional[str] = None,
    ):
        self._model_name = model_name
        self._model_version = model_version
        self.weights_path = str(Path(weights_path).resolve()) if weights_path else ""
        self._device = device or self._detect_best_device()
        self._model = None
        self._load_attempted = False

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def supported_classes(self) -> List[str]:
        return list(self.SUPPORTED_CATEGORIES)

    @property
    def device(self) -> str:
        return self._device

    def _detect_best_device(self) -> str:
        """Detects hardware accelerator (MPS on Mac, CUDA on Linux/Windows, CPU fallback)."""
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    def is_available(self) -> bool:
        """Returns True only if the specified weights file exists on disk."""
        if not self.weights_path:
            return False
        p = Path(self.weights_path)
        return p.exists() and p.is_file() and p.stat().st_size > 0

    def load(self) -> None:
        """Loads weights into memory once."""
        if self._model is not None:
            return

        if not self.is_available():
            raise ModelWeightsMissingError(self.weights_path)

        try:
            from ultralytics import YOLO
            self._model = YOLO(self.weights_path)
            self._load_attempted = True
        except ImportError as e:
            raise ModelNotAvailableError("Package 'ultralytics' is not installed in the environment.") from e
        except Exception as e:
            raise ModelNotAvailableError(f"Failed to load YOLO weights from '{self.weights_path}': {e}") from e

    def predict(self, image: Image.Image, conf_threshold: float = 0.40) -> List[RawPrediction]:
        """Runs YOLO object detection inference."""
        if not self.is_available():
            raise ModelWeightsMissingError(self.weights_path)

        if self._model is None:
            self.load()

        try:
            # Predict using ultralytics YOLO
            results = self._model.predict(
                image,
                conf=conf_threshold,
                device=self._device,
                verbose=False,
            )[0]

            predictions: List[RawPrediction] = []
            if results.boxes is not None:
                for box in results.boxes:
                    conf = float(box.conf[0])
                    if conf < conf_threshold:
                        continue

                    cls_id = int(box.cls[0])
                    # Map class name if available in model.names
                    raw_name = results.names.get(cls_id, "pothole") if hasattr(results, "names") else "pothole"
                    norm_name = "pothole" if "pothole" in raw_name.lower() else "road_damage"

                    # xyxy coordinates in original image space
                    coords = box.xyxy[0].tolist()
                    predictions.append(
                        RawPrediction(
                            class_name=norm_name,
                            confidence=round(conf, 4),
                            box_xyxy=(float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])),
                        )
                    )

            return predictions

        except Exception as e:
            raise CivicLensError(f"Inference execution failed: {e}") from e


class MockModelProvider(BaseModelProvider):
    """
    Deterministic test provider for automated integration testing and offline verification.
    Never used to return fake detections in production.
    """

    def __init__(
        self,
        canned_predictions: Optional[List[RawPrediction]] = None,
        model_name: str = "mock-yolov8",
        model_version: str = "v1.0.0-test",
        is_ready: bool = True,
    ):
        self._predictions = canned_predictions or []
        self._model_name = model_name
        self._model_version = model_version
        self._is_ready = is_ready

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def supported_classes(self) -> List[str]:
        return ["pothole", "road_damage"]

    def is_available(self) -> bool:
        return self._is_ready

    def load(self) -> None:
        if not self._is_ready:
            raise ModelWeightsMissingError("mock_weights.pt")

    def set_predictions(self, preds: List[RawPrediction]) -> None:
        self._predictions = preds

    def predict(self, image: Image.Image, conf_threshold: float = 0.40) -> List[RawPrediction]:
        if not self._is_ready:
            raise ModelWeightsMissingError("mock_weights.pt")
        # Filter by threshold
        return [p for p in self._predictions if p.confidence >= conf_threshold]
