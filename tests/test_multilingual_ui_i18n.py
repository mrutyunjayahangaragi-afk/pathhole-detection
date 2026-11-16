"""
Tests for Multilingual Frontend i18n & Layout Integrity
========================================================
Verifies translation dictionary completeness between English and Kannada,
template script integration, and Unicode string integrity.
"""

import json
import re
from pathlib import Path
import pytest


@pytest.fixture
def i18n_js_content():
    path = Path("frontend/static/js/i18n.js")
    assert path.exists(), "i18n.js missing"
    return path.read_text(encoding="utf-8")


def test_i18n_dictionary_key_symmetry(i18n_js_content):
    """Verifies that English and Kannada dictionaries have identical key coverage."""
    # Extract en dictionary block
    en_match = re.search(r"en:\s*\{(.*?)\},\s*kn:", i18n_js_content, re.DOTALL)
    assert en_match, "en dictionary not found in i18n.js"
    en_keys = set(re.findall(r'"([^"]+)":', en_match.group(1)))

    # Extract kn dictionary block
    kn_match = re.search(r"kn:\s*\{(.*?)\}\s*\n\s*\};", i18n_js_content, re.DOTALL)
    assert kn_match, "kn dictionary not found in i18n.js"
    kn_keys = set(re.findall(r'"([^"]+)":', kn_match.group(1)))

    assert len(en_keys) >= 30, f"Expected at least 30 keys, found {len(en_keys)}"
    missing_in_kn = en_keys - kn_keys
    missing_in_en = kn_keys - en_keys

    assert not missing_in_kn, f"Keys missing in Kannada dictionary: {missing_in_kn}"
    assert not missing_in_en, f"Keys missing in English dictionary: {missing_in_en}"


def test_kannada_unicode_rendering_integrity(i18n_js_content):
    """Verifies that Kannada translations contain valid Kannada Unicode codepoints."""
    kn_match = re.search(r"kn:\s*\{(.*?)\}\s*\n\s*\};", i18n_js_content, re.DOTALL)
    assert kn_match
    kn_text = kn_match.group(1)

    # Check for Kannada codepoints (0x0C80 - 0x0CFF)
    has_kannada_chars = any(0x0C80 <= ord(c) <= 0x0CFF for c in kn_text)
    assert has_kannada_chars, "Kannada dictionary must contain authentic Kannada Unicode codepoints"

    # Specific essential civic phrases
    assert "ರಸ್ತೆ" in kn_text  # road
    assert "ಗುಂಡಿ" in kn_text  # pothole
    assert "ಚರಂಡಿ" in kn_text  # drainage
    assert "ದೀಪ" in kn_text    # streetlight


def test_frontend_templates_include_i18n_js():
    """Verifies that all citizen and navigation templates include i18n.js."""
    templates = [
        "frontend/citizen-report.html",
        "frontend/report-detail.html",
        "frontend/citizen-dashboard.html",
        "frontend/my-reports.html",
        "frontend/index.html",
    ]

    for tmpl in templates:
        p = Path(tmpl)
        assert p.exists(), f"Template {tmpl} does not exist"
        content = p.read_text(encoding="utf-8")
        assert "i18n.js" in content, f"Template {tmpl} must include i18n.js"
        assert "nav.js" in content, f"Template {tmpl} must include nav.js"
