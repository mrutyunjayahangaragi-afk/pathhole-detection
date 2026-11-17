"""Tests for CivicLens Official Branding Replacement and Asset Verification.

Validates:
1. Master branding assets exist in frontend/static/images/branding/.
2. Master logo preserves original dimensions (1024x341), RGBA mode, and true alpha transparency.
3. Master emblem is square and has alpha transparency.
4. WebP, Apple touch icon, and multi-size favicon variants exist.
5. Desktop navigation (nav.js) implements the full official logo with picture fallback.
6. CSS enforces object-fit: contain and aspect-ratio preservation without distortion.
7. Homepage hero, Citizen login, Municipal official login, and Gateway all use the official logo.
8. All frontend HTML files link the official favicon and apple-touch-icon.
"""

import os
import re
from PIL import Image

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
BRANDING_DIR = os.path.join(FRONTEND_DIR, "static", "images", "branding")
CSS_PATH = os.path.join(FRONTEND_DIR, "static", "css", "civiclens.css")
NAV_JS_PATH = os.path.join(FRONTEND_DIR, "static", "js", "nav.js")


def test_master_branding_assets_exist():
    expected_files = [
        "civiclens-logo.png",
        "civiclens-logo.webp",
        "civiclens-emblem.png",
        "civiclens-emblem.webp",
        "civiclens-emblem-192.png",
        "apple-touch-icon.png",
        "favicon-32x32.png",
        "favicon-16x16.png",
        "favicon.ico",
    ]
    for filename in expected_files:
        filepath = os.path.join(BRANDING_DIR, filename)
        assert os.path.exists(filepath), f"Missing branding asset: {filename}"
        assert os.path.getsize(filepath) > 0, f"Asset is empty: {filename}"


def test_master_logo_integrity_and_transparency():
    logo_path = os.path.join(BRANDING_DIR, "civiclens-logo.png")
    with Image.open(logo_path) as img:
        assert img.size == (1024, 341), f"Unexpected logo dimensions: {img.size}"
        assert img.mode == "RGBA", f"Expected RGBA mode, got: {img.mode}"
        alpha = img.split()[-1]
        extrema = alpha.getextrema()
        assert extrema[0] == 0, "Expected alpha channel to contain true transparency (0)"
        assert extrema[1] > 200, "Expected alpha channel to contain visible content"


def test_emblem_integrity_and_square_proportions():
    emblem_path = os.path.join(BRANDING_DIR, "civiclens-emblem.png")
    with Image.open(emblem_path) as img:
        assert img.width == img.height, f"Emblem must be square: {img.size}"
        assert img.mode == "RGBA", f"Expected RGBA mode, got: {img.mode}"
        alpha = img.split()[-1]
        extrema = alpha.getextrema()
        assert extrema[0] == 0, "Emblem must have transparent background"


def test_css_sidebar_and_hero_rules():
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        css = f.read()

    assert ".cl-sidebar-brand-img" in css
    assert "object-fit: contain" in css
    assert "1024 / 341" in css or "1024/341" in css
    assert ".cl-hero-logo" in css
    assert ".cl-mobile-emblem" in css


def test_desktop_nav_renders_official_logo():
    with open(NAV_JS_PATH, "r", encoding="utf-8") as f:
        nav_js = f.read()

    assert "civiclens-logo.png" in nav_js
    assert "civiclens-logo.webp" in nav_js
    assert "cl-sidebar-brand-img" in nav_js
    assert "CL</div>" not in nav_js, "Old text CL badge should not be in nav.js brand header"


def test_homepage_hero_uses_official_logo_without_duplicate():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert "civiclens-logo.png" in html
    assert "cl-hero-logo" in html
    assert 'Civic<span class="hero-tag">Lens</span>' not in html, "Duplicate large CivicLens heading should be removed"


def test_auth_pages_use_official_logo():
    auth_pages = [
        "login.html",
        "citizen-login.html",
        "municipal/login.html",
    ]
    for page in auth_pages:
        filepath = os.path.join(FRONTEND_DIR, page)
        with open(filepath, "r", encoding="utf-8") as f:
            html = f.read()
        assert "civiclens-logo.png" in html, f"{page} missing official civiclens-logo.png"
        assert 'rect width="48" height="48"' not in html, f"{page} still has obsolete placeholder SVG"


def test_all_pages_have_favicon_links():
    html_files = [
        "index.html",
        "login.html",
        "citizen-login.html",
        "citizen-dashboard.html",
        "citizen-report.html",
        "my-reports.html",
        "report-detail.html",
        "public-map.html",
        "public-incident.html",
        "notifications.html",
        "transparency.html",
        "auth-callback.html",
        "municipal/login.html",
        "municipal/dashboard.html",
        "municipal/verification.html",
        "municipal/departments.html",
        "municipal/incident-console.html",
        "municipal/match-review.html",
    ]
    favicon_pattern = re.compile(r'<link\s+rel=["\'](?:shortcut\s+)?icon["\']', re.IGNORECASE)
    apple_pattern = re.compile(r'<link\s+rel=["\']apple-touch-icon["\']', re.IGNORECASE)

    for rel_path in html_files:
        filepath = os.path.join(FRONTEND_DIR, rel_path)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert favicon_pattern.search(content), f"{rel_path} missing favicon link tag"
        assert apple_pattern.search(content), f"{rel_path} missing apple-touch-icon link tag"
