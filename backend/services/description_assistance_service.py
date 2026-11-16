"""
AI Description Assistance Service
=================================
Generates concise complaint summaries, suggests categories across Kannada and
English inputs, and identifies missing context advisory flags without hallucinating
facts or overwriting citizen-selected categories.
"""

import json
import re
import uuid
from typing import Dict, Any, List, Optional, Tuple

from backend.db.engine import get_session_factory
from backend.db.models import AIDescriptionAssistance


CATEGORY_KEYWORDS = {
    "pothole": [
        "pothole", "potholes", "crater", "craters", "depression", "gundi", "ಗುಂಡಿ",
        "ಗುಂಡಿಗಳು", "road cavity"
    ],
    "road_damage": [
        "asphalt", "cave-in", "surface damage", "road crack", "tar eroded", "raste halagide",
        "ರಸ್ತೆ ಹಾಳಾಗಿದೆ", "ರಸ್ತೆ ಕಿತ್ತುಹೋಗಿದೆ", "boulder", "road sinking"
    ],
    "bridge_damage": [
        "bridge", "flyover", "overpass", "expansion joint", "bridge pier", "setuve",
        "ಸೇತುವೆ", "ಮೇಲ್ಸೇತುವೆ"
    ],
    "garbage": [
        "garbage", "debris", "trash", "waste", "rubbish", "dump", "kasa", "ಕಸ",
        "ಕಸದ ರಾಶಿ", "kachra"
    ],
    "water_leakage": [
        "water leak", "pipeline leak", "bwssb", "pipe burst", "potable water",
        "neeru sorike", "ನೀರು ಸೋರಿಕೆ", "ನೀರು ಸೋರುತ್ತಿದೆ", "drinking water"
    ],
    "drainage": [
        "drainage", "storm drain", "sewer", "sewage", "manhole", "overflowing drain",
        "charandi", "ಚರಂಡಿ", "ಚರಂಡಿ ಮುಚ್ಚಳ", "ಮ್ಯಾನ್‌ಹೋಲ್", "clogged drain"
    ],
    "broken_streetlight": [
        "streetlight", "street light", "lamp post", "electrical pole", "dark street",
        "beedi deepa", "ಬೀದಿ ದೀಪ", "ದೀಪ ಹಾಳಾಗಿದೆ", "no lighting"
    ],
}


class DescriptionAssistanceService:
    """Provides non-blocking AI assistance for civic defect reports."""

    MODEL_NAME = "civiclens_semantic_assist_v1"
    MODEL_VERSION = "1.0.0"
    PROVIDER_NAME = "civic_rule_assist"

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def generate_summary(self, text: Optional[str], language: str = "en") -> str:
        """
        Extracts a concise, fact-faithful one-sentence summary.
        Never introduces facts or landmarks absent from the original text.
        """
        if not text or not text.strip():
            return "Civic infrastructure issue reported."

        clean = text.strip()
        sentences = re.split(r"[.!?\n]+", clean)
        first_sentence = sentences[0].strip() if sentences else clean

        # If description is already brief, return it cleaned
        if len(clean) <= 90:
            return clean

        # If first sentence captures the problem clearly
        if 15 <= len(first_sentence) <= 120:
            return first_sentence

        # Summarize by extracting primary defect keyword and context
        for cat, kw_list in CATEGORY_KEYWORDS.items():
            for kw in kw_list:
                kw_low = kw.lower()
                is_matched = (kw_low in clean.lower()) if any(ord(c) > 127 for c in kw_low) else bool(re.search(rf"\b{re.escape(kw_low)}\b", clean, re.IGNORECASE))
                if is_matched:
                    # Find near landmark context if present
                    match_near = re.search(r"(?:near|opposite|opp|beside|at|ಹತ್ತಿರ|ಮುಂದೆ)\s+([A-Za-z0-9\s\u0C80-\u0CFF]{3,35})", clean, re.IGNORECASE)
                    if match_near:
                        context = match_near.group(1).strip()
                        return f"{kw.capitalize()} reported near {context}."
                    return f"{kw.capitalize()} reported on the roadway."

        # Fallback truncation to 100 characters with ellipsis
        return clean[:97].rsplit(" ", 1)[0] + "..."

    def suggest_category(self, text: Optional[str], language: str = "en") -> Tuple[Optional[str], float]:
        """
        Analyzes keywords across Kannada, English, and Mixed inputs to suggest a category.
        Returns (suggested_category, confidence). Returns (None, 0.0) if uncertain.
        """
        if not text or not text.strip():
            return None, 0.0

        clean = text.lower()
        best_cat = None
        highest_score = 0

        for cat, keywords in CATEGORY_KEYWORDS.items():
            matches = 0
            for kw in keywords:
                kw_low = kw.lower()
                if any(ord(c) > 127 for c in kw_low):
                    if kw_low in clean:
                        matches += 1
                else:
                    if re.search(rf"\b{re.escape(kw_low)}\b", clean):
                        matches += 1
            if matches > highest_score:
                highest_score = matches
                best_cat = cat

        if best_cat and highest_score >= 1:
            confidence = min(0.95, 0.65 + (highest_score * 0.15))
            return best_cat, confidence

        return None, 0.0

    def identify_missing_info(
        self, text: Optional[str], has_location: bool = True, has_evidence: bool = True
    ) -> List[str]:
        """
        Identifies missing context to assist citizen with non-blocking suggestions.
        """
        flags = []
        if not text or len(text.strip()) < 15:
            flags.append("short_description")

        clean = text.lower() if text else ""
        has_landmark = bool(
            re.search(r"(?:near|opp|opposite|beside|behind|next to|pillar|gate|stop|ಹತ್ತಿರ|ಮುಂದೆ)", clean)
        )
        if not has_landmark:
            flags.append("missing_landmark")

        has_dimension = bool(
            re.search(r"(?:feet|ft|meter|metre|cm|inch|deep|depth|wide|width|size|ದೊಡ್ಡ|ಆಳ|ಸಣ್ಣ)", clean)
        )
        if not has_dimension:
            flags.append("missing_defect_dimensions")

        if not has_evidence:
            flags.append("no_photo_attached")

        return flags

    def process_and_persist_assistance(
        self,
        report_id: str,
        text: str,
        language: str = "en",
        report_item_id: Optional[str] = None,
        has_location: bool = True,
        has_evidence: bool = True,
    ) -> Dict[str, Any]:
        """
        Computes summary, category suggestion, and missing info flags,
        then safely persists to ai_description_assistance table.
        """
        summary = self.generate_summary(text, language)
        suggested_cat, confidence = self.suggest_category(text, language)
        missing_flags = self.identify_missing_info(text, has_location, has_evidence)

        db = self._session_factory()
        try:
            record = AIDescriptionAssistance(
                id=str(uuid.uuid4()),
                report_id=report_id,
                report_item_id=report_item_id,
                summary=summary,
                suggested_category=suggested_cat,
                missing_info_flags=json.dumps(missing_flags),
                output_language=language,
                provider_name=self.PROVIDER_NAME,
                model_name=self.MODEL_NAME,
                model_version=self.MODEL_VERSION,
                processing_status="completed",
            )
            db.add(record)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

        return {
            "summary": summary,
            "suggested_category": suggested_cat,
            "category_confidence": round(confidence, 4),
            "missing_info_flags": missing_flags,
            "output_language": language,
        }
