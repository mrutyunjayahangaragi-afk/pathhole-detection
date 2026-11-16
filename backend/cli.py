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
from backend.db.models import User, Municipality, Department
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
