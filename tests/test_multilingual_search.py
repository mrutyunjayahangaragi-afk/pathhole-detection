"""
Tests for Multilingual Search & Privacy Isolation
==================================================
Verifies search queries across Kannada, English, translations, reference codes,
and strict role-based access control.
"""

import uuid
import pytest
from backend.services.multilingual_search_service import MultilingualSearchService
from backend.services.citizen_report_service import CitizenReportService
from backend.services.auth_service import AuthService
from backend.db.engine import get_session_factory
from backend.db.models import CitizenReport, ReportItem, User


@pytest.fixture
def auth_service():
    return AuthService()


@pytest.fixture
def report_service():
    return CitizenReportService()


@pytest.fixture
def search_service():
    return MultilingualSearchService()


def test_multilingual_search_and_privacy(auth_service, report_service, search_service):
    # 1. Register two citizens and one officer
    uid1 = uuid.uuid4().hex[:6]
    c1 = auth_service.register_citizen(
        display_name=f"Citizen A {uid1}",
        email=f"cit_a_{uid1}@example.com",
        password="Password123!",
        confirm_password="Password123!",
    )

    uid2 = uuid.uuid4().hex[:6]
    c2 = auth_service.register_citizen(
        display_name=f"Citizen B {uid2}",
        email=f"cit_b_{uid2}@example.com",
        password="Password123!",
        confirm_password="Password123!",
    )

    db = get_session_factory()()
    officer_user = User(
        id=str(uuid.uuid4()),
        display_name="Officer Raman",
        email=f"officer_{uid1}@bbmp.gov.in",
        role="municipal_officer",
    )
    db.add(officer_user)
    db.commit()

    # Retrieve user ORM objects
    user1 = db.query(User).filter_by(id=c1["id"]).first()
    user2 = db.query(User).filter_by(id=c2["id"]).first()
    officer = db.query(User).filter_by(id=officer_user.id).first()
    db.close()

    # 2. Citizen 1 submits Kannada report
    rep1 = report_service.create_report(
        citizen_id=user1.id,
        title="ರಸ್ತೆ ಗುಂಡಿ",
        description="ನಮ್ಮ ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಬಿದ್ದಿದೆ, ಶಾಲಾ ಮಕ್ಕಳಿಗೆ ತೊಂದರೆಯಾಗಿದೆ",
        category="pothole",
        latitude=12.9716,
        longitude=77.5946,
        original_language="kn",
    )

    # 3. Citizen 2 submits English report
    rep2 = report_service.create_report(
        citizen_id=user2.id,
        title="Open drainage near metro",
        description="Drainage manhole cover is missing near Indiranagar metro station",
        category="drainage",
        latitude=12.9784,
        longitude=77.6408,
        original_language="en",
    )

    # 4. Search by Kannada keyword as Citizen 1 (should find rep1 only)
    res_kn = search_service.search_reports(query="ಗುಂಡಿ", requesting_user=user1)
    assert res_kn["total"] == 1
    assert res_kn["reports"][0]["id"] == rep1["id"]

    # 5. Search by English translated keyword ("pothole") as Citizen 1 (matches translated_description)
    res_trans = search_service.search_reports(query="pothole", requesting_user=user1)
    assert res_trans["total"] == 1
    assert res_trans["reports"][0]["id"] == rep1["id"]

    # 6. Privacy Isolation: Citizen 1 searches for Citizen 2's report -> returns 0 results
    res_cross = search_service.search_reports(query="drainage", requesting_user=user1)
    assert res_cross["total"] == 0

    # 7. Municipal Officer searches across all citizens
    res_officer_drain = search_service.search_reports(query="drainage", requesting_user=officer)
    assert res_officer_drain["total"] >= 1
    assert any(r["id"] == rep2["id"] for r in res_officer_drain["reports"])

    res_officer_kn = search_service.search_reports(query="ಗುಂಡಿ", requesting_user=officer)
    assert res_officer_kn["total"] >= 1
    assert any(r["id"] == rep1["id"] for r in res_officer_kn["reports"])

    # 8. Search by exact report reference code
    ref_code = rep1["report_reference"]
    res_ref = search_service.search_reports(query=ref_code, requesting_user=user1)
    assert res_ref["total"] == 1
    assert res_ref["reports"][0]["report_reference"] == ref_code
