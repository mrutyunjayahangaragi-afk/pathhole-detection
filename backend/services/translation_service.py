"""
Translation Service & Providers
===============================
Modular, offline-capable translation service between Kannada (kn) and English (en).
Preserves original text, records model provenance, and handles domain-specific
civic terminology, transliterated mixed text, and graceful failure.
"""

import abc
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from backend.db.engine import get_session_factory
from backend.db.models import ReportTranslation


@dataclass
class TranslationResult:
    source_language: str
    target_language: str
    original_text: str
    translated_text: str
    provider_name: str
    model_name: str
    model_version: str
    status: str  # 'COMPLETED', 'FAILED', 'NEEDS_REVIEW', 'NOT_REQUESTED'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_language": self.source_language,
            "target_language": self.target_language,
            "original_text": self.original_text,
            "translated_text": self.translated_text,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "status": self.status,
        }


class BaseTranslationProvider(abc.ABC):
    """Abstract interface for translation providers."""

    @abc.abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        """Translates text from source_lang to target_lang."""
        pass


class CivicRuleAndDictionaryProvider(BaseTranslationProvider):
    """
    High-performance zero-dependency translation provider specialized in
    civic, road, municipal, and infrastructure terminology between Kannada and English.
    """

    PROVIDER_NAME = "civic_rule_dict"
    MODEL_NAME = "civiclens_kn_en_lexicon_v1"
    MODEL_VERSION = "1.0.0"

    # Kannada Unicode -> English mappings
    KN_TO_EN_PHRASES = [
        (r"ದೊಡ್ಡ\s+ಗುಂಡಿ", "large pothole"),
        (r"ಆಳವಾದ\s+ಗುಂಡಿ", "deep pothole"),
        (r"ರಸ್ತೆಯಲ್ಲಿ\s+ಗುಂಡಿ", "pothole on the road"),
        (r"ಚರಂಡಿ\s+ಮುಚ್ಚಳ", "drainage manhole cover"),
        (r"ಚರಂಡಿ\s+(?:ಬ್ಲಾಕ್\s+ಆಗಿದೆ|ಕಟ್ಟಿಕೊಂಡಿದೆ)", "drainage is blocked"),
        (r"ಬೀದಿ\s+ದೀಪ\s+(?:ಹಾಳಾಗಿದೆ|ಉರಿಯುತ್ತಿಲ್ಲ|ಮುರಿದಿದೆ)", "broken streetlight / not working"),
        (r"ನೀರು\s+ಸೋರುತ್ತಿದೆ", "water is leaking"),
        (r"ಕಸದ\s+ರಾಶಿ\s+(?:ಬಿದ್ದಿದೆ|ಹಾಕಲಾಗಿದೆ)", "garbage accumulation on the road"),
        (r"ಸೇತುವೆ\s+ಬಿರುಕು\s+ಬಿಟ್ಟಿದೆ", "bridge has developed cracks"),
        (r"ದ್ವಿಚಕ್ರ\s+ವಾಹನಗಳಿಗೆ\s+ಅಪಾಯ", "hazard for two-wheelers"),
        (r"ಸಂಚಾರಕ್ಕೆ\s+ತೊಂದರೆ", "traffic obstruction"),
    ]

    KN_TO_EN_WORDS = {
        "ರಸ್ತೆ": "road",
        "ರಸ್ತೆಯಲ್ಲಿ": "on the road",
        "ರಸ್ತೆಯ": "of the road",
        "ಗುಂಡಿ": "pothole",
        "ಗುಂಡಿಗಳು": "potholes",
        "ಚರಂಡಿ": "drainage",
        "ನೀರು": "water",
        "ಕಸ": "garbage",
        "ಬೀದಿ": "street",
        "ದೀಪ": "light",
        "ಸೇತುವೆ": "bridge",
        "ಅಪಾಯ": "danger",
        "ದೊಡ್ಡ": "large",
        "ಸಣ್ಣ": "small",
        "ಆಳವಾದ": "deep",
        "ಹಾಳಾಗಿದೆ": "damaged",
        "ಮುರಿದಿದೆ": "broken",
        "ಬಿದ್ದಿದೆ": "sunken",
        "ತುಂಬಿದೆ": "overflowing",
        "ಹತ್ತಿರ": "near",
        "ಮುಂದೆ": "in front of",
        "ವಿರುದ್ಧ": "opposite",
        "ಶಾಲೆ": "school",
        "ಕಾಲೇಜು": "college",
        "ಆಸ್ಪತ್ರೆ": "hospital",
        "ಬಸ್": "bus",
        "ನಿಲ್ದಾಣ": "stop",
        "ಮೆಟ್ರೋ": "metro",
        "ಕಂಬ": "pillar",
        "ನಮ್ಮ": "our",
        "ಇದೆ": "is there",
        "ಇಲ್ಲ": "is not there",
    }

    # English -> Kannada Unicode mappings
    EN_TO_KN_PHRASES = [
        (r"\blarge pothole\b", "ದೊಡ್ಡ ಗುಂಡಿ"),
        (r"\bdeep pothole\b", "ಆಳವಾದ ಗುಂಡಿ"),
        (r"\bpothole on the road\b", "ರಸ್ತೆಯಲ್ಲಿ ಗುಂಡಿ"),
        (r"\bdrainage (?:is )?blocked\b", "ಚರಂಡಿ ಬ್ಲಾಕ್ ಆಗಿದೆ"),
        (r"\bbroken streetlight\b", "ಮುರಿದ ಬೀದಿ ದೀಪ"),
        (r"\bwater (?:is )?leaking\b", "ನೀರು ಸೋರುತ್ತಿದೆ"),
        (r"\bwater leakage\b", "ನೀರು ಸೋರಿಕೆ"),
        (r"\bgarbage accumulation\b", "ಕಸ ಸಂಗ್ರಹಣೆ"),
        (r"\bhazard for vehicles\b", "ವಾಹನಗಳಿಗೆ ಅಪಾಯ"),
    ]

    EN_TO_KN_WORDS = {
        "pothole": "ಗುಂಡಿ",
        "potholes": "ಗುಂಡಿಗಳು",
        "road": "ರಸ್ತೆ",
        "street": "ಬೀದಿ",
        "drainage": "ಚರಂಡಿ",
        "manhole": "ಮ್ಯಾನ್‌ಹೋಲ್",
        "water": "ನೀರು",
        "leakage": "ಸೋರಿಕೆ",
        "garbage": "ಕಸ",
        "debris": "ಕಸ",
        "bridge": "ಸೇತುವೆ",
        "streetlight": "ಬೀದಿ ದೀಪ",
        "lamp": "ದೀಪ",
        "hazard": "ಅಪಾಯ",
        "danger": "ಅಪಾಯ",
        "large": "ದೊಡ್ಡ",
        "deep": "ಆಳವಾದ",
        "small": "ಸಣ್ಣ",
        "damaged": "ಹಾಳಾಗಿದೆ",
        "broken": "ಮುರಿದಿದೆ",
        "near": "ಹತ್ತಿರ",
        "opposite": "ವಿರುದ್ಧ",
        "school": "ಶಾಲೆ",
        "college": "ಕಾಲೇಜು",
        "hospital": "ಆಸ್ಪತ್ರೆ",
        "bus": "ಬಸ್",
        "stop": "ನಿಲ್ದಾಣ",
        "metro": "ಮೆಟ್ರೋ",
        "pillar": "ಕಂಬ",
    }

    # Transliterated (Manglish/Kanglish) pattern mappings to clean English
    TRANSLIT_TO_EN_PATTERNS = [
        (r"(?i)\broad\s+alli\s+dodda\s+pothole\s+ide\b", "There is a large pothole on the road."),
        (r"(?i)\bnear\s+([a-z0-9\s]+)\s+road\s+drainage\s+block\s+(?:agide|aagide|ಆಗಿದೆ)\b", r"Drainage is blocked near \1 road."),
        (r"(?i)\bnamma\s+rasthe(?:yalli)?\s+dodda\s+gundi\s+ide\b", "There is a large pothole on our road."),
        (r"(?i)\bdodda\s+pothole\s+ide\b", "There is a large pothole."),
        (r"(?i)\bgundi\s+ide\b", "There is a pothole."),
        (r"(?i)\bcharandi\s+block\s+agide\b", "Drainage is blocked."),
        (r"(?i)\bwater\s+leakage\s+ide\b", "There is water leakage."),
        (r"(?i)\bdeepa\s+uriya?thilla\b", "Streetlight is not working."),
    ]

    def translate(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        if not text or not text.strip():
            return TranslationResult(
                source_language=source_lang,
                target_language=target_lang,
                original_text=text or "",
                translated_text="",
                provider_name=self.PROVIDER_NAME,
                model_name=self.MODEL_NAME,
                model_version=self.MODEL_VERSION,
                status="NOT_REQUESTED",
            )

        clean = text.strip()

        # Handle Mixed / Transliterated text to English
        if source_lang in ("kn-en-mixed", "mixed") or target_lang == "en":
            for pattern, repl in self.TRANSLIT_TO_EN_PATTERNS:
                if re.search(pattern, clean):
                    translated = re.sub(pattern, repl, clean).strip()
                    # Capitalize first letter and ensure ending period
                    if translated and not translated.endswith((".", "!", "?")):
                        translated += "."
                    return TranslationResult(
                        source_language=source_lang,
                        target_language="en",
                        original_text=clean,
                        translated_text=translated[0].upper() + translated[1:],
                        provider_name=self.PROVIDER_NAME,
                        model_name=self.MODEL_NAME,
                        model_version=self.MODEL_VERSION,
                        status="COMPLETED",
                    )

        # Kannada -> English
        if source_lang == "kn" or (source_lang in ("kn-en-mixed", "unknown") and any(0x0C80 <= ord(c) <= 0x0CFF for c in clean)):
            translated = clean
            # Apply phrase replacements
            for pattern, repl in self.KN_TO_EN_PHRASES:
                translated = re.sub(pattern, repl, translated)
            # Apply word replacements
            tokens = re.split(r"(\s+|[.,!?;:])", translated)
            out_tokens = []
            for token in tokens:
                lookup = self.KN_TO_EN_WORDS.get(token)
                out_tokens.append(lookup if lookup else token)
            translated = "".join(out_tokens).strip()

            if translated and not translated.endswith((".", "!", "?")):
                translated += "."
            if translated:
                translated = translated[0].upper() + translated[1:]

            return TranslationResult(
                source_language="kn",
                target_language="en",
                original_text=clean,
                translated_text=translated,
                provider_name=self.PROVIDER_NAME,
                model_name=self.MODEL_NAME,
                model_version=self.MODEL_VERSION,
                status="COMPLETED",
            )

        # English -> Kannada
        if source_lang == "en" and target_lang == "kn":
            translated = clean.lower()
            for pattern, repl in self.EN_TO_KN_PHRASES:
                translated = re.sub(pattern, repl, translated, flags=re.IGNORECASE)
            tokens = re.split(r"(\s+|[.,!?;:])", translated)
            out_tokens = []
            for token in tokens:
                lookup = self.EN_TO_KN_WORDS.get(token.lower())
                out_tokens.append(lookup if lookup else token)
            translated = "".join(out_tokens).strip()

            return TranslationResult(
                source_language="en",
                target_language="kn",
                original_text=clean,
                translated_text=translated,
                provider_name=self.PROVIDER_NAME,
                model_name=self.MODEL_NAME,
                model_version=self.MODEL_VERSION,
                status="COMPLETED",
            )

        # Default fallback: return original text unchanged with NEEDS_REVIEW
        return TranslationResult(
            source_language=source_lang,
            target_language=target_lang,
            original_text=clean,
            translated_text=clean,
            provider_name=self.PROVIDER_NAME,
            model_name=self.MODEL_NAME,
            model_version=self.MODEL_VERSION,
            status="NEEDS_REVIEW",
        )


class TranslationService:
    """Thread-safe translation orchestrator with memory caching and persistence."""

    def __init__(self, provider: Optional[BaseTranslationProvider] = None, session_factory=None):
        self.provider = provider or CivicRuleAndDictionaryProvider()
        self._custom_session_factory = session_factory
        self._lock = threading.Lock()
        self._cache: Dict[Tuple[str, str, str], TranslationResult] = {}

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def translate_text(
        self,
        text: Optional[str],
        source_lang: str = "en",
        target_lang: str = "kn",
        report_id: Optional[str] = None,
        report_item_id: Optional[str] = None,
        persist: bool = False,
    ) -> TranslationResult:
        """
        Translates text from source_lang to target_lang.
        Checks memory cache first and optionally persists to report_translations.
        """
        if not text or not text.strip():
            return TranslationResult(
                source_language=source_lang,
                target_language=target_lang,
                original_text=text or "",
                translated_text="",
                provider_name=getattr(self.provider, "PROVIDER_NAME", "mock"),
                model_name=getattr(self.provider, "MODEL_NAME", "mock"),
                model_version=getattr(self.provider, "MODEL_VERSION", "1.0"),
                status="NOT_REQUESTED",
            )

        clean = text.strip()
        cache_key = (clean, source_lang.lower(), target_lang.lower())

        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        result = self.provider.translate(clean, source_lang, target_lang)

        with self._lock:
            self._cache[cache_key] = result

        if persist and report_id:
            self._persist_translation(report_id, report_item_id, result)

        return result

    def _persist_translation(
        self, report_id: str, report_item_id: Optional[str], result: TranslationResult
    ) -> None:
        """Safely saves a translation record to the database."""
        db = self._session_factory()
        try:
            trans_rec = ReportTranslation(
                id=str(uuid.uuid4()),
                report_id=report_id,
                report_item_id=report_item_id,
                source_language=result.source_language,
                target_language=result.target_language,
                original_text=result.original_text,
                translated_text=result.translated_text,
                provider_name=result.provider_name,
                model_name=result.model_name,
                model_version=result.model_version,
                translation_status=result.status,
                review_status="unreviewed",
            )
            db.add(trans_rec)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
