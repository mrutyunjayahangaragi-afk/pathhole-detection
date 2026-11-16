"""
Tests for AI Description Assistance Service
============================================
Verifies summarization, category suggestions across English and Kannada,
and missing context advisory checks.
"""

import pytest
from backend.services.description_assistance_service import DescriptionAssistanceService


def test_summarization_conciseness_and_faithfulness():
    service = DescriptionAssistanceService()
    long_desc = (
        "There is a deep and wide pothole located right in front of the metro station exit gate. "
        "It collects muddy water every time it rains and multiple scooter drivers have lost their balance. "
        "Please dispatch a maintenance crew immediately before serious injury occurs."
    )
    summary = service.generate_summary(long_desc)
    assert len(summary) < len(long_desc)
    assert "pothole" in summary.lower() or "metro" in summary.lower()


def test_category_suggestion_english():
    service = DescriptionAssistanceService()
    text = "The storm drain and sewer line has overflowed across the pedestrian sidewalk."
    cat, conf = service.suggest_category(text)
    assert cat == "drainage"
    assert conf >= 0.70


def test_category_suggestion_kannada():
    service = DescriptionAssistanceService()
    text = "ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಬಿದ್ದಿದೆ"
    cat, conf = service.suggest_category(text)
    assert cat == "pothole"
    assert conf >= 0.70


def test_missing_info_identification():
    service = DescriptionAssistanceService()
    # Missing landmark and defect dimensions
    flags = service.identify_missing_info("Pothole problem here", has_location=True, has_evidence=False)
    assert "missing_landmark" in flags
    assert "missing_defect_dimensions" in flags
    assert "no_photo_attached" in flags


def test_complete_info_identification():
    service = DescriptionAssistanceService()
    text = "Large 2 feet deep pothole near Indiranagar metro station pillar 14."
    flags = service.identify_missing_info(text, has_location=True, has_evidence=True)
    assert "missing_landmark" not in flags
    assert "missing_defect_dimensions" not in flags
    assert "no_photo_attached" not in flags
