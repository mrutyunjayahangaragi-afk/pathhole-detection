"""
Tests for Safe Redirect and Open-Redirect Prevention
====================================================
Verifies that redirect destinations are strictly sanitized and whitelisted.
"""

from urllib.parse import quote


ALLOWED_ROUTES = {
    "/frontend/citizen-report.html",
    "/frontend/my-reports.html",
    "/frontend/report-detail.html",
    "/frontend/public-map.html",
    "/dashboard/dashboard.html",
    "/frontend/citizen-dashboard.html",
    "/frontend/municipal/dashboard.html",
    "/frontend/index.html",
}


def sanitize_redirect_path(raw_path: str) -> str:
    """Python implementation of the frontend role-navigation sanitizer logic."""
    if not raw_path or not isinstance(raw_path, str):
        return None
    decoded = raw_path.strip()
    if not decoded.startswith("/") or decoded.startswith("//") or decoded.startswith("/\\"):
        return None
    if any(decoded.lower().startswith(prefix) for prefix in ("javascript:", "data:", "vbscript:")):
        return None
    base_path = decoded.split("?")[0].split("#")[0]
    if base_path in ALLOWED_ROUTES:
        return decoded
    return None


def test_safe_citizen_report_redirect_accepted():
    target = "/frontend/citizen-report.html"
    assert sanitize_redirect_path(target) == target

    target_with_query = "/frontend/citizen-report.html?category=pothole"
    assert sanitize_redirect_path(target_with_query) == target_with_query


def test_open_redirect_attacks_rejected():
    # External URLs
    assert sanitize_redirect_path("https://attacker.example.com") is None
    assert sanitize_redirect_path("http://evil.com/phishing") is None
    assert sanitize_redirect_path("//evil.com/fake-login") is None
    assert sanitize_redirect_path("/\\evil.com") is None

    # Protocol injections
    assert sanitize_redirect_path("javascript:alert(1)") is None
    assert sanitize_redirect_path("data:text/html,<script>alert(1)</script>") is None

    # Disallowed internal paths
    assert sanitize_redirect_path("/etc/passwd") is None
    assert sanitize_redirect_path("/admin/super-secret") is None
