"""
Tests for Perceptual Hash Service
=================================
Verifies 64-bit DCT perceptual hash generation, Hamming distance calculations,
and robustness across resizing, compression, and visual differences.
"""

import io
from PIL import Image, ImageDraw
from backend.services.perceptual_hash_service import PerceptualHashService


def create_sample_image(color=(100, 100, 100), shape="circle") -> Image.Image:
    """Helper creating distinct synthetic test images."""
    img = Image.new("RGB", (200, 200), color=color)
    draw = ImageDraw.Draw(img)
    if shape == "circle":
        draw.ellipse([40, 40, 160, 160], fill=(20, 20, 20))
    elif shape == "rectangle":
        draw.rectangle([30, 50, 170, 150], fill=(240, 240, 240))
    elif shape == "triangle":
        draw.polygon([(100, 30), (30, 170), (170, 170)], fill=(200, 50, 50))
    return img


def test_phash_exact_image_has_zero_distance():
    service = PerceptualHashService()
    img = create_sample_image(shape="circle")

    h1 = service.compute_phash(img)
    h2 = service.compute_phash(img)

    assert len(h1) == 16
    assert h1 == h2
    assert service.hamming_distance(h1, h2) == 0
    assert service.similarity(h1, h2) == 1.0


def test_phash_resized_and_recompressed_image_stability():
    service = PerceptualHashService()
    orig = create_sample_image(shape="circle")
    h_orig = service.compute_phash(orig)

    # 1. Resize image (e.g. 200x200 down to 80x80)
    resized = orig.resize((80, 80), Image.Resampling.LANCZOS)
    h_resized = service.compute_phash(resized)
    dist_resize = service.hamming_distance(h_orig, h_resized)
    assert dist_resize <= 6, f"Resized Hamming distance {dist_resize} exceeds threshold"

    # 2. JPEG recompression with quality loss (Q=40)
    buf = io.BytesIO()
    orig.save(buf, format="JPEG", quality=40)
    recompressed = Image.open(io.BytesIO(buf.getvalue()))
    h_recompressed = service.compute_phash(recompressed)
    dist_recomp = service.hamming_distance(h_orig, h_recompressed)
    assert dist_recomp <= 6, f"Recompressed Hamming distance {dist_recomp} exceeds threshold"


def test_phash_distinct_images_have_large_distance():
    service = PerceptualHashService()
    img_circle = create_sample_image(color=(30, 30, 30), shape="circle")
    img_rect = create_sample_image(color=(220, 220, 220), shape="rectangle")

    h_circle = service.compute_phash(img_circle)
    h_rect = service.compute_phash(img_rect)

    dist = service.hamming_distance(h_circle, h_rect)
    sim = service.similarity(h_circle, h_rect)

    assert dist >= 16, f"Distinct images have too low distance: {dist}"
    assert sim < 0.75, f"Similarity {sim} too high for distinct shapes"
