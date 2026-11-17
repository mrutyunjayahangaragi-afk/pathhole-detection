"""
Municipal Showcase Routes
=========================
Administrative and operational endpoints for municipal officers and admins:
- Media upload and SHA-256 asset registration
- Impact showcase curation, moderation, and publication
"""

from flask import Blueprint, request, jsonify, g
from typing import Optional, Dict, Any

from backend.auth import login_required, role_required, get_current_user
from backend.services.showcase_service import ShowcaseService
from backend.errors import ValidationError, NotFoundError

municipal_showcase_bp = Blueprint("municipal_showcase_bp", __name__, url_prefix="/api/municipal/showcase")
_showcase_service = ShowcaseService()

MUNICIPAL_ROLES = ("municipal_officer", "dept_admin", "municipal_admin", "system_admin")
ADMIN_ROLES = ("dept_admin", "municipal_admin", "system_admin")


@municipal_showcase_bp.route("/upload", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def upload_showcase_media():
    """Uploads inspection/repair photo or video to Supabase Storage and creates an asset."""
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file part in the request"}), 400

    file = request.files["file"]
    user = get_current_user()
    user_id = user.get("id") if user else "anonymous"
    user_role = user.get("role") if user else "municipal_officer"

    try:
        res = _showcase_service.upload_media_file(file, uploader_id=user_id, uploader_role=user_role)
        return jsonify({"status": "success", "asset": res}), 201
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Upload failed: {str(e)}"}), 500


@municipal_showcase_bp.route("/items", methods=["GET"])
@role_required(*MUNICIPAL_ROLES)
def list_showcase_items():
    """Lists showcase items for the municipal management interface."""
    pub_status = request.args.get("publication_status", None)
    mod_status = request.args.get("moderation_status", None)
    category = request.args.get("category", None)

    items = _showcase_service.list_municipal_items(
        publication_status=pub_status,
        moderation_status=mod_status,
        category=category,
    )
    return jsonify({"status": "success", "items": items}), 200


@municipal_showcase_bp.route("/items", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def create_showcase_item():
    """Creates a new showcase draft linked to an incident and media asset."""
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    user_id = user.get("id") if user else "anonymous"
    user_role = user.get("role") if user else "municipal_officer"

    title = data.get("title", "").strip()
    if not title:
        return jsonify({"status": "error", "message": "Title is required"}), 400

    public_location_label = data.get("public_location_label", "").strip()
    if not public_location_label:
        return jsonify({"status": "error", "message": "Public location summary is required"}), 400

    storage_object_path = data.get("storage_object_path", "").strip()
    if not storage_object_path:
        return jsonify({"status": "error", "message": "Storage object path or asset file is required"}), 400

    res = _showcase_service.create_showcase_item(
        uploader_id=user_id,
        uploader_role=user_role,
        title=title,
        category=data.get("category", "pothole"),
        public_location_label=public_location_label,
        media_type=data.get("media_type", "IMAGE"),
        storage_object_path=storage_object_path,
        evidence_asset_id=data.get("evidence_asset_id"),
        incident_id=data.get("incident_id"),
        description=data.get("description"),
        before_after_type=data.get("before_after_type", "STANDALONE"),
        sort_order=int(data.get("sort_order", 0)),
        is_featured=bool(data.get("is_featured", False)),
    )
    return jsonify(res), 201


@municipal_showcase_bp.route("/items/<item_id>/submit", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def submit_for_review(item_id: str):
    """Submits a draft item for moderation review."""
    user = get_current_user()
    res = _showcase_service.update_item_status(item_id, "submit", user.get("id"), user.get("role"))
    code = res.pop("code", 200)
    return jsonify(res), code


@municipal_showcase_bp.route("/items/<item_id>/approve", methods=["POST"])
@role_required(*ADMIN_ROLES)
def approve_showcase_item(item_id: str):
    """Approves showcase item for publication (Admins only)."""
    user = get_current_user()
    res = _showcase_service.update_item_status(item_id, "approve", user.get("id"), user.get("role"))
    code = res.pop("code", 200)
    return jsonify(res), code


@municipal_showcase_bp.route("/items/<item_id>/reject", methods=["POST"])
@role_required(*ADMIN_ROLES)
def reject_showcase_item(item_id: str):
    """Rejects showcase item with reason (Admins only)."""
    data = request.get_json(silent=True) or {}
    user = get_current_user()
    res = _showcase_service.update_item_status(
        item_id, "reject", user.get("id"), user.get("role"), reason=data.get("reason")
    )
    code = res.pop("code", 200)
    return jsonify(res), code


@municipal_showcase_bp.route("/items/<item_id>/publish", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def publish_showcase_item(item_id: str):
    """Publishes approved item to the public homepage showcase."""
    user = get_current_user()
    res = _showcase_service.update_item_status(item_id, "publish", user.get("id"), user.get("role"))
    code = res.pop("code", 200)
    return jsonify(res), code


@municipal_showcase_bp.route("/items/<item_id>/unpublish", methods=["POST"])
@role_required(*MUNICIPAL_ROLES)
def unpublish_showcase_item(item_id: str):
    """Unpublishes item from the public homepage."""
    user = get_current_user()
    res = _showcase_service.update_item_status(item_id, "unpublish", user.get("id"), user.get("role"))
    code = res.pop("code", 200)
    return jsonify(res), code


@municipal_showcase_bp.route("/items/<item_id>", methods=["DELETE"])
@role_required(*ADMIN_ROLES)
def archive_showcase_item(item_id: str):
    """Archives/deletes showcase item."""
    user = get_current_user()
    res = _showcase_service.update_item_status(item_id, "archive", user.get("id"), user.get("role"))
    code = res.pop("code", 200)
    return jsonify(res), code
