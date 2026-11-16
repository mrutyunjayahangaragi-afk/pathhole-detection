"""
Tests for Language Detection Service
====================================
Verifies language detection across Kannada, English, Mixed text, short inputs,
and uncertainty handling.
"""

import pytest
from backend.services.language_detection_service import (
    LanguageDetectionService, LanguageDetectionResult
)


def test_english_only_detection():
    text = "Large dangerous pothole on 100 Feet Road Indiranagar near the signal."
    res = LanguageDetectionService.detect_language(text)
    assert res.detected_language == "en"
    assert res.confidence >= 0.80
    assert not res.is_mixed
    assert res.status == "completed"


def test_kannada_only_unicode_detection():
    text = "ನಮ್ಮ ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಬಿದ್ದಿದೆ, ವಾಹನ ಸವಾರರಿಗೆ ತೊಂದರೆಯಾಗಿದೆ."
    res = LanguageDetectionService.detect_language(text)
    assert res.detected_language == "kn"
    assert res.confidence >= 0.80
    assert not res.is_mixed
    assert res.status == "completed"


def test_kannada_english_mixed_script_detection():
    text = "Near college road drainage block ಆಗಿದೆ, neeru thumba overflow aagide."
    res = LanguageDetectionService.detect_language(text)
    assert res.detected_language == "kn-en-mixed"
    assert res.is_mixed is True
    assert res.confidence >= 0.70
    assert res.status == "completed"


def test_kannada_latin_transliterated_mixed_detection():
    text = "Road alli dodda pothole ide, two wheelers ge thumba danger."
    res = LanguageDetectionService.detect_language(text)
    assert res.detected_language == "kn-en-mixed"
    assert res.is_mixed is True
    assert res.status == "completed"


def test_very_short_input_uncertainty():
    res = LanguageDetectionService.detect_language("hi")
    assert res.status == "uncertain"
    assert res.confidence <= 0.40

    res_empty = LanguageDetectionService.detect_language("")
    assert res_empty.status == "uncertain"
    assert res_empty.confidence == 0.0

    res_spaces = LanguageDetectionService.detect_language("   ")
    assert res_spaces.status == "uncertain"
    assert res_spaces.confidence == 0.0


def test_punctuation_and_numbers_only():
    res = LanguageDetectionService.detect_language("12345 !!! ???")
    assert res.status == "uncertain"
    assert res.confidence <= 0.40
