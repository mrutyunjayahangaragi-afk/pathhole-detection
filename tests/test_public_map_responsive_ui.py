"""
Tests for Public Map, Incident Details, and Notifications Responsive UI (Step 9)
================================================================================
Validates viewport meta tags, responsive CSS layouts, media queries,
table-to-card transforms, drawers, and accessibility components across public views.
"""

from pathlib import Path
import pytest

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def test_public_map_html_responsive_structure():
    """Scenario 45-47: Validates public-map.html responsive layout, drawer, and controls."""
    html_file = FRONTEND_DIR / "public-map.html"
    assert html_file.exists()
    content = html_file.read_text(encoding="utf-8")

    # Responsive Viewport
    assert 'meta name="viewport"' in content
    # Leaflet map container
    assert 'id="public-leaflet-map"' in content
    # Search and Filter bar
    assert 'id="map-search-input"' in content
    assert 'id="filter-category"' in content
    assert 'id="filter-status"' in content
    assert 'id="filter-severity"' in content
    # Map/List View Toggle
    assert 'id="btn-toggle-view"' in content
    assert 'id="public-list-view"' in content
    # Bottom Sheet / Drawer
    assert 'id="incident-drawer"' in content
    assert 'id="drawer-follow-btn"' in content
    # Responsive CSS Breakpoint
    assert "@media (min-width: 1024px)" in content
    # i18n & nav scripts
    assert "i18n.js" in content
    assert "nav.js" in content


def test_public_incident_html_structure():
    """Scenario 48: Validates public-incident.html details, evidence pairing, and timeline."""
    html_file = FRONTEND_DIR / "public-incident.html"
    assert html_file.exists()
    content = html_file.read_text(encoding="utf-8")

    assert 'meta name="viewport"' in content
    assert 'id="inc-title"' in content
    assert 'id="inc-ref"' in content
    assert 'id="inc-desc"' in content
    assert 'id="inc-mini-map"' in content
    assert 'id="resolution-card"' in content
    assert 'id="img-before-repair"' in content
    assert 'id="img-after-repair"' in content
    assert 'id="timeline-container"' in content
    assert 'id="btn-follow-incident"' in content


def test_notifications_html_structure():
    """Scenario 49: Validates notifications.html inbox, unread pills, and preference modal."""
    html_file = FRONTEND_DIR / "notifications.html"
    assert html_file.exists()
    content = html_file.read_text(encoding="utf-8")

    assert 'meta name="viewport"' in content
    assert 'id="unread-counter"' in content
    assert 'id="btn-mark-all-read"' in content
    assert 'id="notif-filters"' in content
    assert 'id="notif-list-container"' in content
    assert 'id="modal-prefs"' in content
    assert 'id="pref-in-app"' in content
    assert 'id="pref-email"' in content


def test_transparency_html_structure():
    """Scenario 50: Validates transparency.html open metrics and milestone table."""
    html_file = FRONTEND_DIR / "transparency.html"
    assert html_file.exists()
    content = html_file.read_text(encoding="utf-8")

    assert 'meta name="viewport"' in content
    assert 'id="stat-canonical-incidents"' in content
    assert 'id="stat-citizen-reports"' in content
    assert 'id="stat-resolution-rate"' in content
    assert 'id="stat-avg-hours"' in content
    assert 'id="category-bars"' in content
    assert 'id="status-bars"' in content
    assert 'id="milestones-table-body"' in content
