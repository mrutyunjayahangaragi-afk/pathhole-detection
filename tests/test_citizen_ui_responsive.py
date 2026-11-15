"""Tests for Citizen UI and Responsive Layout Requirements (Step 4).

Validates:
- Viewport meta tags across all citizen interface screens.
- Touch target compliance (>= 44px).
- Navigation links and citizen user pill integration.
- Leaflet map integration in reporting and detail views.
- Idempotency key handling and bilingual language toggles.
- Responsive breakpoints and layout rules.
"""

import os
import re
import pytest

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
CSS_PATH = os.path.join(FRONTEND_DIR, "static", "css", "civiclens.css")
NAV_JS_PATH = os.path.join(FRONTEND_DIR, "static", "js", "nav.js")
AUTH_JS_PATH = os.path.join(FRONTEND_DIR, "static", "js", "citizen-auth.js")

CITIZEN_SCREENS = [
    "citizen-login.html",
    "citizen-dashboard.html",
    "citizen-report.html",
    "my-reports.html",
    "report-detail.html",
]


def test_all_citizen_screens_exist():
    """Verifies that all 5 required citizen screens exist in frontend/."""
    for filename in CITIZEN_SCREENS:
        filepath = os.path.join(FRONTEND_DIR, filename)
        assert os.path.exists(filepath), f"Missing required citizen screen: {filename}"


def test_viewport_meta_tag_present():
    """All screens must declare mobile-first responsive viewport meta tags."""
    viewport_pattern = re.compile(
        r'<meta\s+name=["\']viewport["\']\s+content=["\'][^"\']*width=device-width[^"\']*["\']',
        re.IGNORECASE,
    )
    for filename in CITIZEN_SCREENS:
        filepath = os.path.join(FRONTEND_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert viewport_pattern.search(content), f"{filename} missing responsive viewport meta tag"


def test_touch_target_and_design_system_tokens():
    """Verifies CSS tokens enforce accessible touch targets (>= 44px) and fluid spacing."""
    with open(CSS_PATH, "r", encoding="utf-8") as f:
        css = f.read()

    # 44px touch target token
    assert "--cl-min-touch: 44px" in css
    # Responsive mobile drawer breakpoints
    assert "@media (max-width: 1023px)" in css
    # Tablet/desktop breakpoint
    assert "@media (min-width: 768px)" in css
    # Large desktop support
    assert "--cl-sidebar-width: 240px" in css


def test_citizen_auth_guard_present():
    """Protected screens must reference CivicAuth and verify session authentication."""
    protected_screens = [
        "citizen-dashboard.html",
        "citizen-report.html",
        "my-reports.html",
        "report-detail.html",
    ]
    for filename in protected_screens:
        filepath = os.path.join(FRONTEND_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "citizen-auth.js" in content, f"{filename} must import citizen-auth.js"
        assert "CivicAuth" in content, f"{filename} must use CivicAuth guard"


def test_reporting_dual_location_and_disclaimer():
    """citizen-report.html must feature interactive Leaflet map pin, GPS capture, and severity disclaimer."""
    filepath = os.path.join(FRONTEND_DIR, "citizen-report.html")
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    # Leaflet map
    assert "leaflet" in html.lower()
    assert "pin-map" in html
    # GPS capture button
    assert "btn-get-gps" in html
    # Citizen disclaimer
    assert "Citizen Severity Disclaimer" in html or "disclaimer" in html.lower()
    # Idempotency handling
    assert "idempotency" in html.lower() or "idempotency_key" in html.lower()
    # Multi-file evidence input
    assert 'type="file"' in html
    assert "multiple" in html


def test_bilingual_toggle_kannada_english():
    """citizen-report.html must feature both English and Kannada language toggle buttons."""
    filepath = os.path.join(FRONTEND_DIR, "citizen-report.html")
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    assert "btn-en" in html
    assert "btn-kn" in html
    assert "ಕನ್ನಡ" in html


def test_status_timeline_in_report_detail():
    """report-detail.html must contain visual status timeline stages."""
    filepath = os.path.join(FRONTEND_DIR, "report-detail.html")
    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    assert "timeline-steps" in html
    assert "step-submitted" in html
    assert "step-under_review" in html
    assert "step-acknowledged" in html
    assert "step-in_progress" in html
    assert "step-resolved" in html


def test_navigation_includes_citizen_routes():
    """nav.js must provide navigation links for Citizen Dashboard, Report Defect, and My Submissions."""
    with open(NAV_JS_PATH, "r", encoding="utf-8") as f:
        nav_js = f.read()

    assert "citizen-dashboard.html" in nav_js
    assert "citizen-report.html" in nav_js
    assert "my-reports.html" in nav_js
    assert "cl-nav-user-slot" in nav_js
