"""
Municipal UI and Responsive Layout Test Suite
=============================================
Validates DOM elements, responsive CSS rules, table-to-card mobile transforms,
viewport definitions, and interactive components across all municipal portal views.
"""

from pathlib import Path
import pytest


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "municipal"


def test_municipal_dashboard_html_structure():
    """Validates responsive layout and components in dashboard.html."""
    html_file = FRONTEND_DIR / "dashboard.html"
    assert html_file.exists(), "dashboard.html must exist"
    content = html_file.read_text(encoding="utf-8")

    # Responsive Viewport
    assert 'meta name="viewport"' in content
    # Table-to-card CSS rules for mobile screens
    assert "@media (max-width: 768px)" in content
    assert "data-label" in content
    # Dynamic Metrics IDs
    assert 'id="metric-total"' in content
    assert 'id="metric-verification"' in content
    assert 'id="metric-in-progress"' in content
    assert 'id="metric-on-hold"' in content
    assert 'id="metric-resolved"' in content
    assert 'id="metric-sla"' in content
    # Navigation and Scripts
    assert "i18n.js" in content
    assert "nav.js" in content


def test_incident_console_html_structure():
    """Validates incident console lifecycle panels and before/after evidence pairing."""
    html_file = FRONTEND_DIR / "incident-console.html"
    assert html_file.exists(), "incident-console.html must exist"
    content = html_file.read_text(encoding="utf-8")

    # Viewport
    assert 'meta name="viewport"' in content
    # Multi-column grid on desktop, single column on mobile
    assert "@media (max-width: 1024px)" in content
    # Leaflet map
    assert "leaflet.js" in content
    assert 'id="mini-map"' in content
    # Workflow Panels
    assert "btn-save-department" in content
    assert "btn-save-officer" in content
    assert "btn-submit-inspection" in content
    assert "btn-submit-progress" in content
    assert "btn-submit-resolution" in content
    # Before/After Evidence pairing
    assert "before-evidence-container" in content
    assert "res-photo-file" in content
    # Internal Notes vs Citizen Updates Tabs
    assert "tab-btn-notes" in content
    assert "tab-btn-updates" in content


def test_departments_html_structure():
    """Validates department management and officer onboarding forms."""
    html_file = FRONTEND_DIR / "departments.html"
    assert html_file.exists(), "departments.html must exist"
    content = html_file.read_text(encoding="utf-8")

    assert 'meta name="viewport"' in content
    assert "@media (max-width: 900px)" in content
    assert "dept-name" in content
    assert "dept-code" in content
    assert "officer-name" in content
    assert "officer-email" in content
    assert "officer-role" in content
    assert "officers-tbody" in content


def test_verification_queue_html_structure():
    """Validates human verification comparison layout and triage buttons."""
    html_file = FRONTEND_DIR / "verification.html"
    assert html_file.exists(), "verification.html must exist"
    content = html_file.read_text(encoding="utf-8")

    assert 'meta name="viewport"' in content
    assert "comparison-grid" in content
    assert "btn-verify" in content
    assert "btn-reject" in content
    assert "queue-empty-box" in content
