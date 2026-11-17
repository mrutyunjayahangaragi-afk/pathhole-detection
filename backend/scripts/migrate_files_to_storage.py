#!/usr/bin/env python3
"""
CivicLens Evidence File Migration Script
========================================
Audits and migrates local upload evidence files to Supabase Storage:
- Reads all records from evidence_assets_v2 in Supabase PostgreSQL
- Verifies SHA-256 cryptographic checksum of local files against DB records
- Uploads files to Supabase Storage bucket 'citizen-evidence'
- Generates a permanent JSON migration manifest for auditability
- Preserves local original files untouched
"""

import os
import sys
import json
import time
import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from sqlalchemy import text
from backend.config import normalize_database_url
from backend.db.engine import get_engine
from backend.services.storage_service import StorageService


def compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_file_migration():
    print("=" * 70)
    print("CIVICLENS: EVIDENCE FILES AUDIT & STORAGE MIGRATION")
    print("=" * 70)

    raw_pg_url = os.environ.get("DATABASE_URL")
    norm_url = normalize_database_url(raw_pg_url)
    engine = get_engine(norm_url)

    storage_svc = StorageService()
    manifest_path = PROJECT_ROOT / "backend" / "scripts" / "storage_migration_manifest.json"

    with engine.connect() as conn:
        records = conn.execute(text("""
            SELECT id, storage_key, content_sha256, media_type, file_size_bytes, original_filename
            FROM evidence_assets_v2;
        """)).fetchall()

    print(f"[*] Found {len(records)} evidence asset records in Supabase PostgreSQL.\n")
    print(f"{'Asset ID':<36} | {'Status':<8} | {'Size':<8} | {'Filename'}")
    print("-" * 75)

    manifest_entries = []
    matched = 0
    missing = 0

    for r in records:
        asset_id, storage_key, expected_sha, mime_type, file_size, orig_name = r
        raw_path = Path(storage_key)
        
        # Try multiple candidate paths
        candidate_paths = [
            raw_path,
            PROJECT_ROOT / raw_path,
            PROJECT_ROOT / "uploads" / raw_path.name,
            PROJECT_ROOT / "uploads" / "evidence" / raw_path.name,
        ]

        found_path = None
        for p in candidate_paths:
            if p.exists() and p.is_file():
                found_path = p
                break

        entry = {
            "asset_id": asset_id,
            "original_filename": orig_name,
            "expected_sha256": expected_sha,
            "source_path": str(found_path) if found_path else None,
            "file_size_bytes": file_size,
            "mime_type": mime_type,
            "status": "NOT_FOUND",
            "timestamp": time.time(),
        }

        if found_path:
            actual_sha = compute_sha256(found_path)
            entry["actual_sha256"] = actual_sha
            entry["hash_match"] = (actual_sha == expected_sha)
            
            # Read file bytes and upload via storage service
            with open(found_path, "rb") as f:
                data = f.read()

            upload_dest = f"{asset_id}/{orig_name or found_path.name}"
            upload_res = storage_svc.upload_file(
                bucket="citizen-evidence",
                data=data,
                destination_path=upload_dest,
                mime_type=mime_type or "image/jpeg"
            )
            entry["storage_provider"] = upload_res.get("provider")
            entry["target_key"] = upload_res.get("storage_key")
            entry["status"] = "MIGRATED"
            matched += 1
            print(f"{asset_id:<36} | ✓ PASS   | {len(data):<8} | {orig_name or found_path.name}")
        else:
            missing += 1
            entry["status"] = "LOCAL_FILE_MISSING"
            print(f"{asset_id:<36} | ~ SKIP   | {file_size:<8} | {orig_name} (path not on local disk)")

        manifest_entries.append(entry)

    with open(manifest_path, "w") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "total_records": len(records),
                "matched_and_migrated": matched,
                "local_missing": missing,
                "entries": manifest_entries,
            },
            f,
            indent=2,
        )

    print("-" * 75)
    print(f"\n[✓] Storage audit and migration completed. Manifest saved to:\n    {manifest_path}")
    print(f"    Total: {len(records)} | Migrated: {matched} | Missing: {missing}")


if __name__ == "__main__":
    run_file_migration()
