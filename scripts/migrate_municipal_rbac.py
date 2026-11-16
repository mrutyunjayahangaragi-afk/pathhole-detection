"""
CivicLens Municipal RBAC & Multi-Municipality Migration Script
=============================================================
Safely updates database schema across SQLite and Supabase PostgreSQL.
Adds municipalities, official_invitations, and links departments non-destructively.
Preserves 100% of existing citizen reports, incidents, and detections.
"""

import os
import sys
from sqlalchemy import text
from backend.config import get_config
from backend.db.engine import get_engine, get_session_factory
from backend.db.init_schema import create_all_tables
from backend.db.models import Municipality, Department, OfficialInvitation, User


def run_migration(database_url: str = None):
    print("=" * 60)
    print("CivicLens: Municipal RBAC & Multi-Municipality Migration")
    print("=" * 60)

    cfg = get_config()
    target_url = database_url or (
        cfg.DATABASE_URL if getattr(cfg, "DATABASE_PROVIDER", "sqlite") in ("supabase", "postgresql")
        else f"sqlite:///{cfg.DATABASE_PATH}"
    )

    print(f"Target Database Provider: {getattr(cfg, 'DATABASE_PROVIDER', 'sqlite')}")
    print(f"Target Engine: {target_url.split('@')[-1] if '@' in target_url else target_url}")

    # 1. Initialize schema
    engine = create_all_tables(target_url)
    print("✓ Base schema tables and indexes verified.")

    # 2. Database session operations
    SessionFactory = get_session_factory(target_url)
    db = SessionFactory()
    try:
        # Check / Seed default municipality
        bbmp = db.query(Municipality).filter_by(code="BBMP").first()
        if not bbmp:
            bbmp = Municipality(
                name="Bruhat Bengaluru Mahanagara Palike",
                code="BBMP",
                state="Karnataka",
                status="active"
            )
            db.add(bbmp)
            db.commit()
            db.refresh(bbmp)
            print(f"✓ Created default municipality: {bbmp.name} ({bbmp.code})")
        else:
            print(f"✓ Existing municipality verified: {bbmp.name} ({bbmp.code})")

        # Link departments to BBMP
        depts = db.query(Department).all()
        linked_count = 0
        for d in depts:
            if not d.municipality_id:
                d.municipality_id = bbmp.id
                linked_count += 1
        db.commit()
        print(f"✓ Linked {linked_count} unassigned departments to municipality {bbmp.code}.")

        # Audit stats
        mun_count = db.query(Municipality).count()
        dept_count = db.query(Department).count()
        inv_count = db.query(OfficialInvitation).count()
        user_count = db.query(User).count()

        print("-" * 60)
        print("Migration Summary:")
        print(f"  Municipalities: {mun_count}")
        print(f"  Departments:    {dept_count}")
        print(f"  Users:          {user_count}")
        print(f"  Invitations:    {inv_count}")
        print("✓ Non-destructive migration completed successfully.")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"✗ Migration error: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    db_url = sys.argv[1] if len(sys.argv) > 1 else None
    run_migration(db_url)
