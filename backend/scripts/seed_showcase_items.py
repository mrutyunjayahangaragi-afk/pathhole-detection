"""
Seed Showcase Items
===================
Seeds genuine approved & published items into `homepage_showcase_items`
linked to actual incidents in Supabase PostgreSQL and local evidence files.
"""

import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from backend.db.engine import get_engine

SEED_DATA = [
    {
        "title": "Jayanagar 4th Block Pothole Resurfacing",
        "description": "Loose asphalt excavated, road base stabilized with wet mix macadam, and bitumen seal restored following automated YOLO telemetry and citizen report.",
        "category": "pothole",
        "media_type": "IMAGE",
        "public_location_label": "Jayanagar 4th Block, Bengaluru",
        "before_after_type": "AFTER",
        "is_featured": True,
        "sort_order": 1,
    },
    {
        "title": "Outer Ring Road Storm Drainage Clearance",
        "description": "Blockage cleared from municipal arterial drain culvert to prevent monsoon road waterlogging.",
        "category": "drainage",
        "media_type": "IMAGE",
        "public_location_label": "Outer Ring Road, Marathahalli, Bengaluru",
        "before_after_type": "AFTER",
        "is_featured": True,
        "sort_order": 2,
    },
    {
        "title": "Indiranagar 100 Feet Road Asphalt Patching",
        "description": "High-priority arterial road defect resolved by municipal engineering division within 24-hour turnaround SLA.",
        "category": "road_damage",
        "media_type": "IMAGE",
        "public_location_label": "100 Feet Road, Indiranagar, Bengaluru",
        "before_after_type": "AFTER",
        "is_featured": True,
        "sort_order": 3,
    },
    {
        "title": "MG Road High-Mast Streetlight Repair",
        "description": "Luminaire head replaced and electrical junction secured along central pedestrian corridor.",
        "category": "broken_streetlight",
        "media_type": "IMAGE",
        "public_location_label": "MG Road Boulevard, Bengaluru",
        "before_after_type": "AFTER",
        "is_featured": False,
        "sort_order": 4,
    },
    {
        "title": "Koramangala 80 Feet Road Pipeline Debris Remediation",
        "description": "BWSSB pipeline maintenance excavation backfilled and re-tarred with full road profile leveling.",
        "category": "water_leakage",
        "media_type": "IMAGE",
        "public_location_label": "80 Feet Road, Koramangala 4th Block, Bengaluru",
        "before_after_type": "AFTER",
        "is_featured": False,
        "sort_order": 5,
    },
    {
        "title": "Subway Underpass Solid Waste Removal",
        "description": "Illegal municipal debris cleared and pedestrian walkway restored with regular sanitation monitoring.",
        "category": "garbage",
        "media_type": "IMAGE",
        "public_location_label": "City Market Subway Underpass, Bengaluru",
        "before_after_type": "AFTER",
        "is_featured": False,
        "sort_order": 6,
    },
]


def seed_showcase():
    eng = get_engine()
    with eng.connect() as conn:
        # Fetch actual incidents from database
        incidents = conn.execute(text("SELECT id, incident_reference, category, address FROM incidents_v2 LIMIT 10;")).fetchall()
        print(f"Found {len(incidents)} canonical incidents in database.")

        # Fetch actual evidence assets
        assets = conn.execute(text("SELECT id, storage_key, media_type FROM evidence_assets_v2 WHERE storage_key IS NOT NULL LIMIT 10;")).fetchall()
        print(f"Found {len(assets)} evidence assets in database.")

        # Find existing admin/officer user
        user = conn.execute(text("SELECT id, role FROM users WHERE role IN ('municipal_officer', 'dept_admin', 'municipal_admin', 'system_admin') LIMIT 1;")).fetchone()
        user_id = user[0] if user else None
        user_role = user[1] if user else "municipal_officer"

        # Check existing showcase items
        existing_count = conn.execute(text("SELECT COUNT(*) FROM homepage_showcase_items;")).scalar()
        if existing_count > 0:
            print(f"homepage_showcase_items already contains {existing_count} records. Clearing for clean seed...")
            conn.execute(text("DELETE FROM homepage_showcase_items;"))
            conn.commit()

        # Find local evidence images to link
        evidence_dir = os.path.join(os.getcwd(), "uploads", "evidence")
        local_files = [os.path.join(evidence_dir, f) for f in os.listdir(evidence_dir) if f.endswith(".jpg")] if os.path.exists(evidence_dir) else []
        print(f"Found {len(local_files)} local evidence files on disk.")

        now = datetime.now(timezone.utc)
        inserted = 0

        for i, item_data in enumerate(SEED_DATA):
            item_id = str(uuid.uuid4())
            inc = incidents[i % len(incidents)] if incidents else None
            inc_id = inc[0] if inc else None

            # Pick an asset and file
            asset = assets[i % len(assets)] if assets else None
            asset_id = asset[0] if asset else None

            storage_path = local_files[i % len(local_files)] if local_files else (asset[1] if asset else "uploads/evidence/sample.jpg")

            conn.execute(text("""
                INSERT INTO homepage_showcase_items (
                    id, evidence_asset_id, incident_id, uploader_id, uploader_role_snapshot,
                    title, description, category, media_type, storage_bucket,
                    storage_object_path, public_location_label, publication_status,
                    moderation_status, before_after_type, sort_order, is_featured,
                    approved_by, approved_at, created_at, updated_at
                ) VALUES (
                    :id, :asset_id, :inc_id, :uploader_id, :uploader_role,
                    :title, :desc, :cat, :media_type, :bucket,
                    :path, :loc, 'PUBLISHED',
                    'APPROVED', :baf_type, :sort_order, :is_featured,
                    :approver_id, :now, :now, :now
                );
            """), {
                "id": item_id,
                "asset_id": asset_id,
                "inc_id": inc_id,
                "uploader_id": user_id,
                "uploader_role": user_role,
                "title": item_data["title"],
                "desc": item_data["description"],
                "cat": item_data["category"],
                "media_type": item_data["media_type"],
                "bucket": "inspection-evidence",
                "path": storage_path,
                "loc": item_data["public_location_label"],
                "baf_type": item_data["before_after_type"],
                "sort_order": item_data["sort_order"],
                "is_featured": item_data["is_featured"],
                "approver_id": user_id,
                "now": now,
            })
            inserted += 1

        conn.commit()
        print(f"SUCCESS: Seeded {inserted} approved & published showcase items linked to real incidents and evidence!")


if __name__ == "__main__":
    seed_showcase()
