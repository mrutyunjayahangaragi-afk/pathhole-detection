"""
Tests for Modular Database Repositories
=======================================
Verifies ProfileRepository, OrganizationRepository, RoleRepository, and IncidentRepository.
"""

import pytest
from backend.database.session import get_db_session
from backend.database.repositories import (
    ProfileRepository,
    OrganizationRepository,
    RoleRepository,
    IncidentRepository,
)
from backend.db.models import User, Municipality, Department, Incident


def test_profile_repository_get_and_create(app):
    session = get_db_session()
    try:
        repo = ProfileRepository(session)
        # Test creating Google citizen profile
        user = repo.create_or_sync_google_profile(
            auth_user_id="google-oauth2-test-uid-12345",
            email="citizen.tester@example.com",
            display_name="Citizen Tester",
            preferred_language="kn",
        )
        session.commit()

        assert user.id is not None
        assert user.role == "citizen"
        assert user.preferred_language == "kn"

        # Verify lookup by auth_user_id
        found = repo.get_by_auth_id("google-oauth2-test-uid-12345")
        assert found is not None
        assert found.email == "citizen.tester@example.com"

        # Verify lookup by email
        found_email = repo.get_by_email("citizen.tester@example.com")
        assert found_email is not None
        assert found_email.id == user.id
    finally:
        session.close()


def test_role_repository_permissions(app):
    session = get_db_session()
    try:
        role_repo = RoleRepository(session)
        profile_repo = ProfileRepository(session)

        # Citizen cannot manage departments
        citizen = profile_repo.get_by_email("citizen.tester@example.com")
        assert citizen is not None
        assert role_repo.has_permission(citizen, "report_defect") is True
        assert role_repo.has_permission(citizen, "manage_department") is False

        # System admin has full permissions
        admin = User(
            email="sysadmin.tester@civiclens.gov.in",
            display_name="System Admin",
            role="system_admin",
            is_active=True,
        )
        session.add(admin)
        session.commit()

        assert role_repo.has_permission(admin, "manage_department") is True
        assert role_repo.has_permission(admin, "invite_officer") is True
        assert role_repo.has_permission(admin, "view_audit_logs") is True
    finally:
        session.close()


def test_organization_repository_departments_and_municipalities(app):
    from backend.services.department_management_service import DepartmentManagementService
    DepartmentManagementService().seed_default_departments()

    session = get_db_session()
    try:
        org_repo = OrganizationRepository(session)
        munis = org_repo.list_municipalities()
        assert len(munis) >= 1
        assert munis[0].code == "BBMP"

        depts = org_repo.list_departments(municipality_id=munis[0].id)
        assert len(depts) >= 6
        codes = [d.code for d in depts]
        assert "ROAD_MAINT" in codes
        assert "DRAINAGE" in codes
    finally:
        session.close()


def test_incident_repository_spatial_bbox_query(app):
    session = get_db_session()
    try:
        repo = IncidentRepository(session)
        # Bounding box around Bengaluru
        results = repo.get_public_incidents_in_bbox(
            min_lat=12.80, min_lon=77.40,
            max_lat=13.15, max_lon=77.80,
            limit=50
        )
        assert isinstance(results, list)
    finally:
        session.close()
