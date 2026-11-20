"""
CivicLens Flask CLI Management Commands
=======================================
Provides administrative commands for system bootstrapping, official invitations,
and database operations. Never exposes administrative credentials over public HTTP.
"""

import re
import uuid
import click
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
from flask.cli import AppGroup

from backend.db.engine import get_session_factory
from backend.db.models import User, Municipality, Department, Incident, DepartmentMembership, IncidentAssignment, ReportItem
from backend.logging_config import setup_logging

logger = setup_logging()

civiclens_cli = AppGroup("civiclens", help="CivicLens administrative commands.")


def validate_admin_password(password: str) -> bool:
    """Validates that administrative password meets high-entropy security requirements."""
    if len(password) < 10:
        return False
    if not re.search(r"[A-Za-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[@$!%*#?&_\-\.]", password):
        return False
    return True


@civiclens_cli.command("bootstrap-admin")
@click.option("--email", prompt=True, help="Official administrative email address.")
@click.option("--name", prompt=True, default="System Administrator", help="Display name for the administrator.")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Initial administrative password (minimum 10 characters, mixed alphanumeric + special)."
)
def bootstrap_admin(email: str, name: str, password: str):
    """
    Secure one-time administrative bootstrap command (Stage A onboarding).
    Provisions the initial system_admin account. Refuses duplicate bootstrap if an admin exists.
    """
    email_clean = email.strip().lower()
    if not re.match(r"^[\w\.\+\-]+@(?:[\w\-]+\.)+[a-zA-Z]{2,}$", email_clean):
        click.echo("Error: Invalid email address format.", err=True)
        return

    if not validate_admin_password(password):
        click.echo(
            "Error: Administrative password must be at least 10 characters long "
            "and contain at least one letter, one number, and one special character (@$!%*#?&_-.).",
            err=True
        )
        return

    SessionFactory = get_session_factory()
    db = SessionFactory()
    try:
        # Check if any system_admin already exists
        existing_admin = db.query(User).filter_by(role="system_admin", is_active=True).first()
        if existing_admin:
            click.echo(
                f"Error: A system administrator account already exists ({existing_admin.email}). "
                "Duplicate bootstrap is refused to prevent administrative privilege escalation.",
                err=True
            )
            return

        # Check if email is already used by another role
        existing_user = db.query(User).filter_by(email=email_clean).first()
        pwd_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")
        now = datetime.now(timezone.utc)

        if existing_user:
            existing_user.role = "system_admin"
            existing_user.display_name = name.strip()
            existing_user.password_hash = pwd_hash
            existing_user.is_active = True
            existing_user.updated_at = now
            admin_user = existing_user
        else:
            admin_user = User(
                display_name=name.strip(),
                email=email_clean,
                role="system_admin",
                preferred_language="en",
                password_hash=pwd_hash,
                is_active=True,
                created_at=now,
                updated_at=now
            )
            db.add(admin_user)

        # Ensure default municipality exists
        bbmp = db.query(Municipality).filter_by(code="BBMP").first()
        if not bbmp:
            bbmp = Municipality(
                name="Bruhat Bengaluru Mahanagara Palike",
                code="BBMP",
                state="Karnataka",
                status="active",
                created_at=now,
                updated_at=now
            )
            db.add(bbmp)

        db.commit()
        click.echo(f"✓ Success: System administrator successfully bootstrapped ({admin_user.email}).")
        click.echo("✓ Security Notice: Use the official portal at /frontend/municipal/login.html to sign in.")

    except Exception as e:
        db.rollback()
        click.echo(f"Error during bootstrap: {e}", err=True)
    finally:
        db.close()


@civiclens_cli.command("provision-official")
@click.option("--email", prompt=True, help="Official email address (e.g. officer@bbmp.gov.in).")
@click.option("--name", prompt=True, default="Municipal Officer", help="Full name of official.")
@click.option(
    "--role",
    type=click.Choice(["municipal_officer", "dept_admin", "municipal_admin", "system_admin"]),
    default="municipal_officer",
    prompt=True,
    help="Role to assign."
)
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help="Password (min 8 chars)."
)
def provision_official(email: str, name: str, role: str, password: str):
    """
    Directly provisions or updates an authorized municipal official account.
    Safe backend-only administrative action.
    """
    email_clean = email.strip().lower()
    if len(password) < 8:
        click.echo("Error: Password must be at least 8 characters.", err=True)
        return

    db = get_session_factory()()
    try:
        now = datetime.now(timezone.utc)
        pwd_hash = generate_password_hash(password)
        u = db.query(User).filter_by(email=email_clean).first()
        if u:
            u.role = role
            u.display_name = name.strip()
            u.password_hash = pwd_hash
            u.is_active = True
            u.updated_at = now
            action = "Updated existing user as official"
        else:
            u = User(
                id=str(uuid.uuid4()),
                display_name=name.strip(),
                email=email_clean,
                role=role,
                preferred_language="en",
                password_hash=pwd_hash,
                is_active=True,
                created_at=now,
                updated_at=now
            )
            db.add(u)
            action = "Created new official user"

        db.commit()
        click.echo(f"✓ Success: {action} ({u.email}) with role '{u.role}'.")
        click.echo("✓ You can now sign in at http://localhost:5055/frontend/municipal-login.html")
    except Exception as e:
        db.rollback()
        click.echo(f"Error provisioning official: {e}", err=True)
    finally:
        db.close()


@civiclens_cli.command("audit-demo-data")
def audit_demo_data():
    """
    Audits synthetic demo data, duplicate departments, and unlinked intake items.
    """
    db = get_session_factory()()
    try:
        # 1. Vikram synthetic accounts
        vikrams = db.query(User).filter(User.email.like("vikram_%@civiclens.gov.in")).all()
        active_vikrams = [v for v in vikrams if v.is_active]

        # 2. Duplicate departments
        dup_depts = db.query(Department).filter(Department.code.in_(["LIGHTING", "SANITATION"])).all()

        # 3. Legacy telemetry incidents (without report items)
        subq = db.query(ReportItem.incident_id).filter(ReportItem.incident_id.isnot(None)).distinct()
        legacy_incidents = db.query(Incident).filter(~Incident.id.in_(subq)).all()
        legacy_unprovenanced = [inc for inc in legacy_incidents if inc.provenance != "IMPORTED_LEGACY_DATA"]

        # 4. Unlinked citizen reports
        unlinked_items = db.query(ReportItem).filter(ReportItem.incident_id.is_(None)).count()

        click.echo("=" * 60)
        click.echo("CIVICLENS DATABASE AUDIT REPORT")
        click.echo("=" * 60)
        click.echo(f"Synthetic 'Engineer Vikram' accounts: {len(vikrams)} total ({len(active_vikrams)} active)")
        click.echo(f"Duplicate/deprecated departments:     {len(dup_depts)} ({[d.code for d in dup_depts]})")
        click.echo(f"Legacy telemetry incidents (no items): {len(legacy_incidents)} total ({len(legacy_unprovenanced)} needing provenance tag)")
        click.echo(f"Unlinked citizen report items:         {unlinked_items} awaiting triage")
        click.echo("=" * 60)

    finally:
        db.close()


@civiclens_cli.command("cleanup-demo-data")
@click.option("--execute", is_flag=True, default=False, help="Perform actual changes in database.")
def cleanup_demo_data(execute: bool):
    """
    Consolidates synthetic officials into a canonical account, deactivates duplicate departments,
    and marks legacy sensor detections with provenance tags to fix SLA calculations.
    """
    mode = "EXECUTE" if execute else "DRY RUN"
    click.echo(f"Running CivicLens Demo Data Cleanup [{mode}]...")

    db = get_session_factory()()
    try:
        now = datetime.now(timezone.utc)

        # 1. Consolidate Duplicate Departments
        lighting = db.query(Department).filter_by(code="LIGHTING").first()
        streetlight = db.query(Department).filter_by(code="STREETLIGHT").first()
        sanitation = db.query(Department).filter_by(code="SANITATION").first()
        solid_waste = db.query(Department).filter_by(code="SOLID_WASTE").first()

        if lighting and streetlight:
            click.echo(f"Consolidating department LIGHTING -> STREETLIGHT ({streetlight.id})")
            if execute:
                # Re-map any memberships or incidents
                db.query(DepartmentMembership).filter_by(department_id=lighting.id).update(
                    {"department_id": streetlight.id}, synchronize_session=False
                )
                db.query(Incident).filter_by(department_id=lighting.id).update(
                    {"department_id": streetlight.id}, synchronize_session=False
                )
                lighting.is_active = False
                lighting.provenance = "DEPRECATED_DUPLICATE"

        if sanitation and solid_waste:
            click.echo(f"Consolidating department SANITATION -> SOLID_WASTE ({solid_waste.id})")
            if execute:
                db.query(DepartmentMembership).filter_by(department_id=sanitation.id).update(
                    {"department_id": solid_waste.id}, synchronize_session=False
                )
                db.query(Incident).filter_by(department_id=sanitation.id).update(
                    {"department_id": solid_waste.id}, synchronize_session=False
                )
                sanitation.is_active = False
                sanitation.provenance = "DEPRECATED_DUPLICATE"

        # 2. Canonical Engineer Vikram
        canonical_email = "vikram@civiclens.gov.in"
        canonical_vikram = db.query(User).filter_by(email=canonical_email).first()
        if not canonical_vikram:
            click.echo(f"Creating canonical official account: {canonical_email}")
            if execute:
                canonical_vikram = User(
                    id=str(uuid.uuid4()),
                    display_name="Engineer Vikram",
                    email=canonical_email,
                    role="municipal_officer",
                    provenance="CANONICAL",
                    password_hash=generate_password_hash("OfficerPass123!"),
                    is_active=True,
                    created_at=now,
                    updated_at=now
                )
                db.add(canonical_vikram)
                db.flush()
        else:
            click.echo(f"Found canonical official account: {canonical_vikram.id}")
            if execute:
                canonical_vikram.is_active = True
                canonical_vikram.display_name = "Engineer Vikram"
                canonical_vikram.provenance = "CANONICAL"

        # Link canonical Vikram to ROAD_MAINT department
        road_dept = db.query(Department).filter_by(code="ROAD_MAINT").first()
        if road_dept and execute and canonical_vikram:
            mem = db.query(DepartmentMembership).filter_by(
                user_id=canonical_vikram.id, department_id=road_dept.id
            ).first()
            if not mem:
                db.add(DepartmentMembership(
                    id=str(uuid.uuid4()),
                    user_id=canonical_vikram.id,
                    department_id=road_dept.id,
                    role_in_dept="officer",
                    is_active=True,
                    joined_at=now
                ))

        # Reassign from synthetic vikram accounts
        synthetic_vikrams = db.query(User).filter(User.email.like("vikram_%@civiclens.gov.in")).all()
        synth_ids = [v.id for v in synthetic_vikrams]
        click.echo(f"Found {len(synth_ids)} synthetic Vikram accounts to quarantine")

        if execute and canonical_vikram and synth_ids:
            # Reassign incidents
            reassigned_inc = db.query(Incident).filter(Incident.assigned_officer_id.in_(synth_ids)).update(
                {"assigned_officer_id": canonical_vikram.id}, synchronize_session=False
            )
            click.echo(f"Reassigned {reassigned_inc} incidents to canonical {canonical_email}")

            # Reassign incident_assignments
            reassigned_assign = db.query(IncidentAssignment).filter(IncidentAssignment.assigned_to.in_(synth_ids)).update(
                {"assigned_to": canonical_vikram.id}, synchronize_session=False
            )
            click.echo(f"Reassigned {reassigned_assign} assignment records to canonical {canonical_email}")

            # Quarantine synthetic accounts
            db.query(User).filter(User.id.in_(synth_ids)).update(
                {"is_active": False, "provenance": "TEST_FIXTURE"}, synchronize_session=False
            )
            click.echo(f"Quarantined {len(synth_ids)} synthetic user accounts (is_active=False)")

        # 3. Provenance Tag for Legacy Telemetry Incidents (No Citizen Report Items)
        subq = db.query(ReportItem.incident_id).filter(ReportItem.incident_id.isnot(None)).distinct()
        legacy_incidents = db.query(Incident).filter(~Incident.id.in_(subq)).all()
        click.echo(f"Found {len(legacy_incidents)} legacy vehicle telemetry incidents")

        if execute:
            for inc in legacy_incidents:
                inc.provenance = "IMPORTED_LEGACY_DATA"
            click.echo(f"Tagged {len(legacy_incidents)} incidents as provenance='IMPORTED_LEGACY_DATA'")

        if execute:
            db.commit()
            click.echo("✓ Cleanup successfully committed to database.")
        else:
            db.rollback()
            click.echo("✓ Dry run complete. Use --execute to apply changes.")

    except Exception as e:
        db.rollback()
        click.echo(f"Error during cleanup: {e}", err=True)
    finally:
        db.close()


