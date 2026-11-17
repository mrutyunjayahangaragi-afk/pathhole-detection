"""
Supabase PostgreSQL Persistence & Server Restart Verification
=============================================================
Tests end-to-end data persistence across application restarts:
1. Create citizen report through backend service/API
2. Confirm row is inserted into Supabase PostgreSQL
3. Simulate application restart (engine disposal and session recreation)
4. Retrieve the record again from Supabase PostgreSQL
5. Confirm data integrity and field preservation
"""

import os
import uuid
import time
import pytest
from sqlalchemy import text

from datetime import datetime, timezone

from backend.config import get_config, normalize_database_url
from backend.db.engine import get_engine, reset_engine
from backend.database.session import get_db_session
from backend.db.models import CitizenReport, Incident, User, TelemetryDevice


@pytest.mark.skipif(
    os.environ.get("DATABASE_PROVIDER") != "supabase" or os.environ.get("TESTING") == "true",
    reason="Only runs when explicitly targeting live Supabase in production/integration mode"
)
def test_supabase_persistence_across_engine_restart():
    """Verifies that records written to Supabase persist after disposing and recreating the engine."""
    cfg = get_config()
    test_ref = f"TST-{uuid.uuid4().hex[:8].upper()}"
    test_report_id = str(uuid.uuid4())
    test_user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Step 1: Write directly via Session into Supabase PostgreSQL
    session = get_db_session()
    try:
        # Create a test user first to satisfy foreign key
        user = User(
            id=test_user_id,
            email=f"tester_{test_ref.lower()}@civiclens.local",
            display_name="Supabase Persistence Tester",
            role="citizen",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        session.flush()

        # Create citizen report
        report = CitizenReport(
            id=test_report_id,
            citizen_id=test_user_id,
            report_reference=test_ref,
            title="Pothole near MG Road Metro",
            description="Deep pothole causing vehicular congestion",
            reported_severity="severe",
            latitude=12.9716,
            longitude=77.5946,
            address="MG Road, Bengaluru",
            original_language="en",
            submission_channel="web",
            status="submitted",
            submitted_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(report)
        session.commit()
    finally:
        session.close()

    # Step 2: Simulate application / engine restart
    reset_engine()

    # Step 3: Re-open a fresh session from fresh engine connection
    fresh_session = get_db_session()
    try:
        fetched_report = fresh_session.query(CitizenReport).filter_by(id=test_report_id).first()
        assert fetched_report is not None, "Report was not persisted in Supabase!"
        assert fetched_report.report_reference == test_ref
        assert fetched_report.reported_severity == "severe"
        assert abs(fetched_report.latitude - 12.9716) < 0.0001
        assert fetched_report.address == "MG Road, Bengaluru"

        # Verify foreign key user relationship
        fetched_user = fresh_session.query(User).filter_by(id=test_user_id).first()
        assert fetched_user is not None
        assert fetched_user.display_name == "Supabase Persistence Tester"
    finally:
        # Step 4: Clean up test rows
        fresh_session.execute(text(f"DELETE FROM citizen_reports_v2 WHERE id = '{test_report_id}';"))
        fresh_session.execute(text(f"DELETE FROM users WHERE id = '{test_user_id}';"))
        fresh_session.commit()
        fresh_session.close()


if __name__ == "__main__":
    import os
    os.environ["DATABASE_PROVIDER"] = "supabase"
    os.environ.pop("TESTING", None)
    print("Testing Supabase persistence across restart...")
    test_supabase_persistence_across_engine_restart()
    print("SUCCESS: Supabase persistence verified across engine reset!")
