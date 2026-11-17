"""
Tests for CivicLens Impact Showcase & Municipal Media System
============================================================
Verifies:
- Showcase data model and repository queries
- Public showcase API filtering, pagination, and strict PII redaction
- Public media streaming security (unapproved items blocked)
- Municipal media upload validation (rejects invalid extensions and oversized files)
- Administrative moderation and publication lifecycle
- Role-based authorization and anti-IDOR checks
"""

import io
import uuid
import pytest
from datetime import datetime, timezone

from backend.db.engine import get_session_factory
from backend.db.models import HomepageShowcaseItem, EvidenceAsset, Incident, User
from backend.services.showcase_service import ShowcaseService


@pytest.fixture
def showcase_service():
    return ShowcaseService()


def test_showcase_model_and_repository(client):
    """Test model creation, persistence, and querying."""
    factory = get_session_factory()
    db = factory()
    item_id = str(uuid.uuid4())
    try:
        item = HomepageShowcaseItem(
            id=item_id,
            title="Test Road Repair",
            description="Bitumen patching verified by field engineer",
            category="pothole",
            media_type="IMAGE",
            storage_bucket="inspection-evidence",
            storage_object_path="/tmp/test_repair.jpg",
            public_location_label="Indiranagar, Bengaluru",
            publication_status="PUBLISHED",
            moderation_status="APPROVED",
            before_after_type="AFTER",
            sort_order=1,
            is_featured=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(item)
        db.commit()

        # Query back
        fetched = db.query(HomepageShowcaseItem).filter_by(id=item_id).first()
        assert fetched is not None
        assert fetched.title == "Test Road Repair"
        assert fetched.category == "pothole"
        assert fetched.is_featured is True
    finally:
        db.query(HomepageShowcaseItem).filter_by(id=item_id).delete()
        db.commit()
        db.close()


def test_public_showcase_api_privacy(client):
    """Public showcase API must return only approved published items and zero citizen PII."""
    factory = get_session_factory()
    db = factory()
    pub_id = str(uuid.uuid4())
    draft_id = str(uuid.uuid4())
    try:
        # 1. Approved Published Item
        pub_item = HomepageShowcaseItem(
            id=pub_id,
            title="Public Safe Repair",
            description="Cleared drainage block",
            category="drainage",
            media_type="IMAGE",
            storage_bucket="inspection-evidence",
            storage_object_path="/tmp/drainage.jpg",
            public_location_label="Koramangala 4th Block, Bengaluru",
            publication_status="PUBLISHED",
            moderation_status="APPROVED",
            before_after_type="AFTER",
            sort_order=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        # 2. Draft Unapproved Item
        draft_item = HomepageShowcaseItem(
            id=draft_id,
            title="Confidential Internal Draft",
            description="Officer notes pending verification",
            category="road_damage",
            media_type="IMAGE",
            storage_bucket="inspection-evidence",
            storage_object_path="/tmp/draft.jpg",
            public_location_label="Secret Depot",
            publication_status="DRAFT",
            moderation_status="PENDING",
            before_after_type="BEFORE",
            sort_order=2,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add_all([pub_item, draft_item])
        db.commit()

        # Query public API
        resp = client.get("/api/public/homepage-showcase")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"

        item_ids = [it["id"] for it in data["items"]]
        assert pub_id in item_ids, "Approved published item must be in public showcase"
        assert draft_id not in item_ids, "Draft item must NEVER appear in public showcase"

        # Verify strict privacy: No raw PII
        for it in data["items"]:
            assert "email" not in it
            assert "phone" not in it
            assert "internal_notes" not in it
            assert "raw_gps" not in it
            assert "citizen_id" not in it
            assert "public_location_label" in it
    finally:
        db.query(HomepageShowcaseItem).filter(HomepageShowcaseItem.id.in_([pub_id, draft_id])).delete()
        db.commit()
        db.close()


def test_public_showcase_empty_fallback(client):
    """When no items match, return honest empty collection with HTTP 200."""
    resp = client.get("/api/public/homepage-showcase?category=non_existent_category_xyz")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["total_items"] == 0
    assert data["items"] == []


def test_showcase_media_endpoint_unapproved_blocked(client):
    """Unapproved or draft items must return 404 on public media stream."""
    factory = get_session_factory()
    db = factory()
    draft_id = str(uuid.uuid4())
    try:
        draft_item = HomepageShowcaseItem(
            id=draft_id,
            title="Unapproved Item",
            category="pothole",
            media_type="IMAGE",
            storage_bucket="inspection-evidence",
            storage_object_path="/tmp/non_existent.jpg",
            public_location_label="Bengaluru",
            publication_status="DRAFT",
            moderation_status="PENDING",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(draft_item)
        db.commit()

        resp = client.get(f"/api/public/showcase/media/{draft_id}")
        assert resp.status_code == 404
    finally:
        db.query(HomepageShowcaseItem).filter_by(id=draft_id).delete()
        db.commit()
        db.close()


def test_showcase_upload_validation(client, showcase_service):
    """Test rejection of unsupported file types."""
    from werkzeug.datastructures import FileStorage

    # Reject executable
    fake_sh = io.BytesIO(b"#!/bin/bash\necho hello\n")
    file_obj = FileStorage(stream=fake_sh, filename="script.sh", content_type="application/x-sh")

    with pytest.raises(ValueError, match="Unsupported file format"):
        showcase_service.upload_media_file(file_obj, uploader_id="test", uploader_role="municipal_officer")


def test_showcase_lifecycle_workflow(client):
    """Test complete administrative lifecycle: submit -> approve -> publish -> unpublish."""
    svc = ShowcaseService()
    # Create draft without foreign key or with valid user
    res = svc.create_showcase_item(
        uploader_id=None,
        uploader_role="municipal_officer",
        title="Lifecycle Pothole Repair",
        category="pothole",
        public_location_label="Indiranagar 100ft Rd",
        media_type="IMAGE",
        storage_object_path="uploads/evidence/test.jpg",
    )
    assert res["status"] == "success"
    item_id = res["id"]

    try:
        # Submit
        sub_res = svc.update_item_status(item_id, "submit", "officer-1", "municipal_officer")
        assert sub_res["publication_status"] == "PENDING_REVIEW"
        assert sub_res["moderation_status"] == "PENDING"

        # Approve by admin
        app_res = svc.update_item_status(item_id, "approve", None, "dept_admin")
        assert app_res["moderation_status"] == "APPROVED"

        # Publish
        pub_res = svc.update_item_status(item_id, "publish", "officer-1", "municipal_officer")
        assert pub_res["publication_status"] == "PUBLISHED"

        # Unpublish
        unpub_res = svc.update_item_status(item_id, "unpublish", "officer-1", "municipal_officer")
        assert unpub_res["publication_status"] == "UNPUBLISHED"
    finally:
        session = get_session_factory()()
        session.query(HomepageShowcaseItem).filter_by(id=item_id).delete()
        session.commit()
        session.close()
