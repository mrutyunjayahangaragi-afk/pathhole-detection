"""
Public Showcase Routes
======================
Endpoints delivering public approved CivicLens Impact Showcase media.
Strictly redacts all personal identifiable information, raw GPS, and internal data.
"""

from flask import Blueprint, request, jsonify, send_file, abort
import os

from backend.services.showcase_service import ShowcaseService

public_showcase_bp = Blueprint("public_showcase", __name__, url_prefix="/api/public")
_showcase_service = ShowcaseService()


@public_showcase_bp.route("/homepage-showcase", methods=["GET"])
def get_homepage_showcase():
    """
    Returns approved and published showcase items for the homepage carousel
    and before-and-after comparison cards.
    """
    category = request.args.get("category", None)
    before_after_type = request.args.get("before_after_type", None)
    featured_only = request.args.get("featured", "").lower() in ("true", "1")
    try:
        limit = min(int(request.args.get("limit", 20)), 50)
    except ValueError:
        limit = 20

    items = _showcase_service.get_public_showcase(
        category=category,
        before_after_type=before_after_type,
        featured_only=featured_only,
        limit=limit,
    )

    return jsonify({
        "status": "success",
        "total_items": len(items),
        "items": items,
    }), 200


@public_showcase_bp.route("/showcase/media/<item_id>", methods=["GET"])
def get_showcase_media(item_id: str):
    """
    Streams public-safe media file with HTTP caching headers.
    Returns HTTP 404/403 if item is not approved/published or not found.
    """
    as_thumb = request.args.get("thumb", "").lower() in ("true", "1")
    file_path, mime_type = _showcase_service.get_media_file_info(item_id, as_thumb=as_thumb)

    if not file_path or not os.path.exists(file_path):
        abort(404, description="Showcase media not found or not approved for public viewing.")

    response = send_file(file_path, mimetype=mime_type or "application/octet-stream")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response
