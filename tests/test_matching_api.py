"""
API Integration & Authorization Tests for Matching Engine
=========================================================
Tests RESTful endpoints for candidate evaluation, review queue,
confirming links/new incidents, and strictly verifies anti-IDOR authorization.
"""

import uuid
from backend.app import create_app
from backend.db.engine import get_session_factory
from backend.db.models import Incident, CitizenReport, ReportItem, User, MatchEvaluation, MatchCandidate, MatchDecision
from backend.services.auth_service import AuthService


def _create_user_with_token(client, email: str, role: str) -> tuple[str, str]:
    auth = AuthService()
    uid = f"user-{uuid.uuid4().hex[:8]}"
    pwd = "SecurePassword123!"
    u = auth.register_citizen(
        display_name=f"Test {role.capitalize()}",
        email=email,
        password=pwd,
        confirm_password=pwd,
        preferred_language="en",
    )
    # Update role if staff
    if role != "citizen":
        factory = get_session_factory()
        db = factory()
        db_user = db.query(User).filter_by(id=u["id"]).first()
        db_user.role = role
        db.commit()
        db.close()

    res = client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    token = res.get_json()["token"]
    return u["id"], token


def test_matching_api_flow_and_anti_idor():
    app = create_app()
    client = app.test_client()
    factory = get_session_factory()

    officer_email = f"officer_{uuid.uuid4().hex[:6]}@bbmp.gov.in"
    citizen1_email = f"citizen1_{uuid.uuid4().hex[:6]}@test.com"
    citizen2_email = f"citizen2_{uuid.uuid4().hex[:6]}@test.com"

    officer_id, officer_token = _create_user_with_token(client, officer_email, "municipal_officer")
    citizen1_id, citizen1_token = _create_user_with_token(client, citizen1_email, "citizen")
    citizen2_id, citizen2_token = _create_user_with_token(client, citizen2_email, "citizen")

    db = factory()
    # Create existing incident
    inc = Incident(
        id=str(uuid.uuid4()),
        incident_reference="INC-TEST-API",
        category="pothole",
        latitude=12.9716,
        longitude=77.5946,
        report_count=1,
    )
    # Create report owned by citizen1
    rep1 = CitizenReport(
        id=str(uuid.uuid4()),
        citizen_id=citizen1_id,
        latitude=12.9716,
        longitude=77.5946,
        status="submitted",
    )
    item1 = ReportItem(
        id=str(uuid.uuid4()),
        report_id=rep1.id,
        category="pothole",
        description="Deep pothole test",
        status="pending",
    )
    db.add_all([inc, rep1, item1])
    db.commit()
    db.close()

    try:
        # 1. Citizen 2 tries to evaluate Citizen 1's report item -> 403 Forbidden (Anti-IDOR)
        res_idor = client.post(
            f"/api/v1/matching/evaluate/{item1.id}",
            headers={"Authorization": f"Bearer {citizen2_token}"}
        )
        assert res_idor.status_code == 403

        # 2. Citizen 1 evaluates their own report item -> 200 OK
        res_eval = client.post(
            f"/api/v1/matching/evaluate/{item1.id}",
            headers={"Authorization": f"Bearer {citizen1_token}"}
        )
        assert res_eval.status_code == 200
        data = res_eval.get_json()["data"]
        eval_id = data["evaluation_id"]
        assert eval_id is not None
        assert data["candidate_count"] >= 1
        assert data["candidates"][0]["candidate_incident_id"] == inc.id

        # 3. Citizen 1 tries to access review queue -> 403 Forbidden (Staff only)
        res_q_citizen = client.get(
            "/api/v1/matching/queue",
            headers={"Authorization": f"Bearer {citizen1_token}"}
        )
        assert res_q_citizen.status_code == 403

        # 4. Municipal Officer accesses review queue -> 200 OK
        res_q_officer = client.get(
            "/api/v1/matching/queue",
            headers={"Authorization": f"Bearer {officer_token}"}
        )
        assert res_q_officer.status_code == 200
        queue_items = res_q_officer.get_json()["data"]["items"]
        assert any(it["report_item_id"] == item1.id for it in queue_items)

        # 5. Citizen 1 tries to confirm link -> 403 Forbidden (Staff only)
        res_confirm_citizen = client.post(
            "/api/v1/matching/confirm-link",
            headers={"Authorization": f"Bearer {citizen1_token}"},
            json={
                "report_item_id": item1.id,
                "incident_id": inc.id,
                "review_notes": "Attempting unauthorized confirmation",
            }
        )
        assert res_confirm_citizen.status_code == 403

        # 6. Municipal Officer confirms link -> 200 OK
        res_confirm_officer = client.post(
            "/api/v1/matching/confirm-link",
            headers={"Authorization": f"Bearer {officer_token}"},
            json={
                "report_item_id": item1.id,
                "incident_id": inc.id,
                "evaluation_id": eval_id,
                "review_notes": "Municipal engineer verified identical defect",
            }
        )
        assert res_confirm_officer.status_code == 200
        assert res_confirm_officer.get_json()["data"]["new_report_count"] == 2

    finally:
        cleanup_db = factory()
        cleanup_db.query(MatchDecision).filter_by(report_item_id=item1.id).delete(synchronize_session=False)
        cleanup_db.query(MatchCandidate).filter_by(candidate_incident_id=inc.id).delete(synchronize_session=False)
        cleanup_db.query(MatchEvaluation).filter_by(report_item_id=item1.id).delete(synchronize_session=False)
        cleanup_db.query(ReportItem).filter_by(id=item1.id).delete(synchronize_session=False)
        cleanup_db.query(CitizenReport).filter_by(id=rep1.id).delete(synchronize_session=False)
        cleanup_db.query(Incident).filter_by(id=inc.id).delete(synchronize_session=False)
        cleanup_db.query(User).filter(User.id.in_([officer_id, citizen1_id, citizen2_id])).delete(synchronize_session=False)
        cleanup_db.commit()
        cleanup_db.close()
