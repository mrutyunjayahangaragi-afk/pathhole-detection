"""
Perceptual Hash Service
=======================
Pure-Python, Pillow-based Discrete Cosine Transform (DCT) Perceptual Hash (pHash).

Computes a robust 64-bit perceptual fingerprint of an image that remains stable across:
- Resizing and aspect-ratio adjustments
- JPEG recompression and quality reduction
- Minor contrast and gamma variations
- Watermarking or subtle color alterations

Algorithm:
1. Normalize to 32x32 grayscale image.
2. Compute 2D Discrete Cosine Transform (DCT-II).
3. Extract top-left 8x8 low-frequency matrix (64 coefficients).
4. Compute median of the 64 coefficients (excluding DC term).
5. Build 64-bit binary hash (1 if coeff > median else 0) formatted as 16-char hex.
6. Similarity is measured by Hamming distance d in [0, 64].
"""

import math
from pathlib import Path
from typing import Union, Optional
from PIL import Image
import io


class PerceptualHashService:
    """Perceptual hashing service using 2D Discrete Cosine Transform (pHash)."""

    HASH_SIZE = 8       # 8x8 low-frequency DCT block -> 64 bits
    IMG_SIZE = 32       # 32x32 pre-DCT sampling resolution
    ALGORITHM = "dct_phash"
    VERSION = "v1.0"

    def __init__(self):
        # Precompute 1D DCT basis matrix for 32x32 to maximize execution speed
        self._dct_basis = self._build_dct_basis(self.IMG_SIZE)

    @staticmethod
    def _build_dct_basis(n: int):
        """Constructs the n x n DCT-II transformation matrix."""
        matrix = []
        for i in range(n):
            row = []
            alpha = 1.0 / math.sqrt(n) if i == 0 else math.sqrt(2.0 / n)
            for j in range(n):
                row.append(alpha * math.cos(((2 * j + 1) * i * math.pi) / (2.0 * n)))
            matrix.append(row)
        return matrix

    def _apply_2d_dct(self, pixels: list[list[float]]) -> list[list[float]]:
        """Applies 2D DCT-II: D = M * P * M^T where M is the basis matrix."""
        n = self.IMG_SIZE
        # Temp = M * P
        temp = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                s = 0.0
                for k in range(n):
                    s += self._dct_basis[i][k] * pixels[k][j]
                temp[i][j] = s

        # Result = Temp * M^T
        result = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                s = 0.0
                for k in range(n):
                    s += temp[i][k] * self._dct_basis[j][k]
                result[i][j] = s

        return result

    def compute_phash(self, image_input: Union[str, Path, Image.Image, bytes]) -> str:
        """
        Computes the 64-bit hex DCT perceptual hash for an image.

        Args:
            image_input: File path, PIL Image instance, or raw image bytes.

        Returns:
            16-character hexadecimal string representing the 64-bit hash.
        """
        if isinstance(image_input, (str, Path)):
            img = Image.open(str(image_input))
        elif isinstance(image_input, bytes):
            img = Image.open(io.BytesIO(image_input))
        elif isinstance(image_input, Image.Image):
            img = image_input
        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")

        # 1. Convert to grayscale and resize to 32x32 with Lanczos resampling
        resized = img.convert("L").resize((self.IMG_SIZE, self.IMG_SIZE), Image.Resampling.LANCZOS)
        try:
            pixel_data = list(resized.get_flattened_data())
        except AttributeError:
            pixel_data = list(resized.getdata())
        pixels = [pixel_data[i * self.IMG_SIZE:(i + 1) * self.IMG_SIZE] for i in range(self.IMG_SIZE)]

        # 2. Compute 2D DCT
        dct_matrix = self._apply_2d_dct(pixels)

        # 3. Extract top-left 8x8 low-frequency components
        low_freq = []
        for r in range(self.HASH_SIZE):
            for c in range(self.HASH_SIZE):
                low_freq.append(dct_matrix[r][c])

        # Exclude DC coefficient (top-left [0,0]) when calculating the median
        ac_coeffs = low_freq[1:]
        sorted_coeffs = sorted(ac_coeffs)
        mid = len(sorted_coeffs) // 2
        median = (sorted_coeffs[mid] + sorted_coeffs[mid - 1]) / 2.0

        # 4. Generate 64-bit hash: 1 if >= median else 0
        bit_val = 0
        for i, val in enumerate(low_freq):
            if val > median:
                bit_val |= (1 << (63 - i))

        return f"{bit_val:016x}"

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """
        Calculates Hamming distance (bit differences) between two 16-hex hashes.
        Result is in range [0, 64].
        """
        try:
            val1 = int(hash1, 16)
            val2 = int(hash2, 16)
        except (ValueError, TypeError):
            return 64
        return (val1 ^ val2).bit_count()

    @classmethod
    def similarity(cls, hash1: Optional[str], hash2: Optional[str]) -> float:
        """
        Normalized perceptual similarity in range [0.0, 1.0].
        1.0 means identical perceptual hash (distance 0).
        0.0 means completely inverted perceptual hash (distance 64).
        """
        if not hash1 or not hash2:
            return 0.0
        dist = cls.hamming_distance(hash1, hash2)
        return max(0.0, min(1.0, 1.0 - (dist / 64.0)))
