"""
Language Intelligence API Routes
================================
Provides endpoints for language detection, translation requests,
translation retrieval, and AI description assistance.
"""

from flask import Blueprint, request, jsonify, g
from backend.services.language_detection_service import LanguageDetectionService
from backend.services.translation_service import TranslationService
from backend.services.description_assistance_service import DescriptionAssistanceService
from backend.auth import login_required
from backend.db.engine import get_session_factory
from backend.db.models import ReportTranslation, CitizenReport
from backend.errors import ValidationError, NotFoundError

language_bp = Blueprint("language_bp", __name__, url_prefix="/api/v1/language")
detection_service = LanguageDetectionService()
translation_service = TranslationService()
assistance_service = DescriptionAssistanceService()


@language_bp.route("/detect", methods=["POST"])
def detect_language():
    """
    Detects language of input text (Kannada, English, Mixed, or Unknown).
    Non-blocking and handles short descriptions with explicit uncertainty.
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    res = detection_service.detect_language(text)
    return jsonify({
        "status": "success",
        "detection": res.to_dict(),
    }), 200


@language_bp.route("/translate", methods=["POST"])
def translate_text():
    """
    On-demand translation between Kannada and English.
    Preserves original text and returns model provenance.
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    source_lang = data.get("source_language", "en")
    target_lang = data.get("target_language", "kn")

    res = translation_service.translate_text(
        text=text,
        source_lang=source_lang,
        target_lang=target_lang,
    )
    return jsonify({
        "status": "success",
        "translation": res.to_dict(),
    }), 200


@language_bp.route("/translations/<report_id>", methods=["GET"])
@login_required
def get_report_translations(report_id):
    """
    Retrieves all stored translations for a specific citizen report.
    Enforces ownership permissions.
    """
    db = get_session_factory()()
    try:
        report = db.query(CitizenReport).filter_by(id=report_id).first()
        if not report:
            raise NotFoundError("Report not found")

        # Permission check: owner or municipal staff
        is_staff = g.current_user.role in ("municipal_officer", "dept_admin", "system_admin")
        if report.citizen_id != g.current_user.id and not is_staff:
            raise NotFoundError("Report not found or access denied")

        translations = db.query(ReportTranslation).filter_by(report_id=report_id).all()
        return jsonify({
            "status": "success",
            "report_id": report_id,
            "original_language": report.original_language,
            "detected_language": report.detected_language,
            "translations": [
                {
                    "id": t.id,
                    "source_language": t.source_language,
                    "target_language": t.target_language,
                    "original_text": t.original_text,
                    "translated_text": t.translated_text,
                    "provider_name": t.provider_name,
                    "model_name": t.model_name,
                    "translation_status": t.translation_status,
                    "review_status": t.review_status,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in translations
            ],
        }), 200
    finally:
        db.close()


@language_bp.route("/assist", methods=["POST"])
@login_required
def get_description_assistance():
    """
    Provides advisory summary, category suggestion, and missing info flags for draft text.
    Non-blocking guidance for citizen complaint drafting.
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    language = data.get("language", "en")
    has_location = bool(data.get("has_location", False))
    has_evidence = bool(data.get("has_evidence", False))

    summary = assistance_service.generate_summary(text, language)
    suggested_cat, confidence = assistance_service.suggest_category(text, language)
    missing_flags = assistance_service.identify_missing_info(text, has_location, has_evidence)

    return jsonify({
        "status": "success",
        "summary": summary,
        "suggested_category": suggested_cat,
        "category_confidence": round(confidence, 4),
        "missing_info_flags": missing_flags,
    }), 200
