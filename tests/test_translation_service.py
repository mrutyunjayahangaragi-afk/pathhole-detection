"""
Tests for Translation Service & Providers
==========================================
Verifies bidirectional translation between Kannada and English,
transliterated mixed expressions, caching, and original text immutability.
"""

import pytest
from backend.services.translation_service import (
    TranslationService, CivicRuleAndDictionaryProvider, TranslationResult
)


def test_kannada_to_english_translation():
    service = TranslationService()
    text = "ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಬಿದ್ದಿದೆ"
    res = service.translate_text(text, source_lang="kn", target_lang="en")

    assert res.status == "COMPLETED"
    assert res.source_language == "kn"
    assert res.target_language == "en"
    assert res.original_text == text  # Immutability
    assert "pothole" in res.translated_text.lower()
    assert "road" in res.translated_text.lower()


def test_english_to_kannada_translation():
    service = TranslationService()
    text = "large pothole on the road"
    res = service.translate_text(text, source_lang="en", target_lang="kn")

    assert res.status == "COMPLETED"
    assert res.source_language == "en"
    assert res.target_language == "kn"
    assert "ಗುಂಡಿ" in res.translated_text
    assert "ರಸ್ತೆ" in res.translated_text


def test_transliterated_mixed_translation():
    service = TranslationService()
    text = "Road alli dodda pothole ide"
    res = service.translate_text(text, source_lang="kn-en-mixed", target_lang="en")

    assert res.status == "COMPLETED"
    assert "pothole" in res.translated_text.lower()
    assert res.original_text == text


def test_empty_or_whitespace_input():
    service = TranslationService()
    res = service.translate_text("", source_lang="en", target_lang="kn")
    assert res.status == "NOT_REQUESTED"
    assert res.translated_text == ""


def test_translation_caching():
    service = TranslationService()
    text = "ಚರಂಡಿ ಮುಚ್ಚಳ ಮುರಿದಿದೆ"
    res1 = service.translate_text(text, source_lang="kn", target_lang="en")
    res2 = service.translate_text(text, source_lang="kn", target_lang="en")

    assert res1 is res2  # Returned directly from memory cache
