"""
Language Detection Service
==========================
Detects Kannada (kn), English (en), and Kannada-English code-switching (mixed)
using Unicode script analysis, local transliteration lexicon checks,
and confidence estimation with explicit uncertainty handling.
"""

import re
from dataclasses import dataclass
from typing import Tuple, Dict, Any, Optional

# Unicode ranges
KANNADA_RANGE = (0x0C80, 0x0CFF)
LATIN_RANGE = (0x0041, 0x007A)

# Common Kannada words written in Latin script (transliteration / Manglish / Kanglish)
KANNADA_LATIN_KEYWORDS = {
    "alli", "illi", "yelli", "ide", "illa", "agide", "aagide", "aythu",
    "dodda", "sanna", "thumba", "tumba", "rasta", "raste", "rastheyalli",
    "gundi", "kade", "hathira", "hatthira", "beku", "beda", "jaaga",
    "neeru", "charandi", "kasa", "deepa", "haalu", "bidtha", "namma",
    "nimma", "ondhu", "eradu", "ooru", "mane", "shaale", "dhaari", "dari"
}


@dataclass
class LanguageDetectionResult:
    detected_language: str  # 'kn', 'en', 'kn-en-mixed', 'unknown'
    confidence: float       # 0.0 to 1.0
    is_mixed: bool
    kannada_ratio: float
    english_ratio: float
    status: str             # 'completed', 'uncertain', 'failed'
    model_name: str = "civiclens_unicode_ngram_v1"
    model_version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected_language": self.detected_language,
            "confidence": round(self.confidence, 4),
            "is_mixed": self.is_mixed,
            "kannada_ratio": round(self.kannada_ratio, 4),
            "english_ratio": round(self.english_ratio, 4),
            "status": self.status,
            "model_name": self.model_name,
            "model_version": self.model_version,
        }


class LanguageDetectionService:
    """Thread-safe language identifier for civic complaints."""

    @staticmethod
    def _count_scripts(text: str) -> Tuple[int, int, int]:
        """Counts Kannada, Latin, and total non-whitespace characters."""
        kn_count = 0
        lat_count = 0
        total_letters = 0

        for char in text:
            cp = ord(char)
            if KANNADA_RANGE[0] <= cp <= KANNADA_RANGE[1]:
                kn_count += 1
                total_letters += 1
            elif (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A):
                lat_count += 1
                total_letters += 1
            elif not char.isspace() and not char.isdigit():
                total_letters += 1

        return kn_count, lat_count, max(1, total_letters)

    @classmethod
    def detect_language(cls, text: Optional[str]) -> LanguageDetectionResult:
        """
        Identifies whether input text is Kannada, English, or Mixed.
        Handles short inputs with uncertainty without forcing false classifications.
        """
        if not text or not text.strip():
            return LanguageDetectionResult(
                detected_language="unknown",
                confidence=0.0,
                is_mixed=False,
                kannada_ratio=0.0,
                english_ratio=0.0,
                status="uncertain",
            )

        clean = text.strip()
        words = re.findall(r"\w+", clean.lower())
        char_count = len(clean)

        # 1. Very short text check (< 3 characters)
        if char_count < 3 or not words:
            return LanguageDetectionResult(
                detected_language="unknown",
                confidence=0.25,
                is_mixed=False,
                kannada_ratio=0.0,
                english_ratio=0.0,
                status="uncertain",
            )

        kn_count, lat_count, total = cls._count_scripts(clean)
        kn_ratio = kn_count / total
        lat_ratio = lat_count / total

        # Check for Latin-script transliterated Kannada
        translit_matches = 0
        for w in words:
            if w in KANNADA_LATIN_KEYWORDS:
                translit_matches += 1

        has_translit = translit_matches >= 1

        # 2. Both scripts significantly present -> Explicit mixed
        if kn_ratio >= 0.15 and lat_ratio >= 0.15:
            return LanguageDetectionResult(
                detected_language="kn-en-mixed",
                confidence=0.88,
                is_mixed=True,
                kannada_ratio=kn_ratio,
                english_ratio=lat_ratio,
                status="completed",
            )

        # 3. Predominantly Kannada script
        if kn_ratio >= 0.60:
            conf = min(0.99, 0.70 + (kn_ratio * 0.29))
            return LanguageDetectionResult(
                detected_language="kn",
                confidence=conf,
                is_mixed=False,
                kannada_ratio=kn_ratio,
                english_ratio=lat_ratio,
                status="completed",
            )

        # 4. Predominantly Latin script with transliterated Kannada words
        if lat_ratio >= 0.60 and has_translit:
            conf = min(0.92, 0.70 + (translit_matches * 0.08))
            return LanguageDetectionResult(
                detected_language="kn-en-mixed",
                confidence=conf,
                is_mixed=True,
                kannada_ratio=kn_ratio,
                english_ratio=lat_ratio,
                status="completed",
            )

        # 5. Predominantly English / Latin
        if lat_ratio >= 0.60:
            conf = min(0.98, 0.75 + (lat_ratio * 0.23))
            return LanguageDetectionResult(
                detected_language="en",
                confidence=conf,
                is_mixed=False,
                kannada_ratio=kn_ratio,
                english_ratio=lat_ratio,
                status="completed",
            )

        # 6. Ambiguous or unsupported scripts
        return LanguageDetectionResult(
            detected_language="unknown",
            confidence=0.35,
            is_mixed=False,
            kannada_ratio=kn_ratio,
            english_ratio=lat_ratio,
            status="uncertain",
        )
