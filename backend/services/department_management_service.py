"""
CivicLens Department & Officer Management Service
=================================================
Manages municipal departments, default seeding, department activation guards,
officer onboarding, department memberships, and officer workload tracking.
"""

from typing import List, Dict, Any, Optional
import uuid
import re
import json
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.db.engine import get_session_factory
from backend.db.models import Department, DepartmentMembership, User, Incident, AuditLog, Municipality
from backend.errors import ValidationError, NotFoundError, CivicLensError


DEFAULT_DEPARTMENTS = [
    {
        "code": "ROAD_MAINT",
        "name": "Road & Highway Maintenance",
        "description": "Responsible for asphalt, potholes, road resurfacing, and pavement repairs.",
        "contact_email": "roads@civiclens.gov.in"
    },
    {
        "code": "DRAINAGE",
        "name": "Stormwater & Drainage Department",
        "description": "Responsible for storm drains, culverts, flood mitigation, and drainage clearing.",
        "contact_email": "drainage@civiclens.gov.in"
    },
    {
        "code": "BWSSB",
        "name": "Water Supply & Sewerage Board",
        "description": "Responsible for water line leaks, manholes, and underground sewage lines.",
        "contact_email": "water@civiclens.gov.in"
    },
    {
        "code": "STREETLIGHT",
        "name": "Electrical & Streetlighting",
        "description": "Responsible for streetlights, electrical poles, and public lighting fixtures.",
        "contact_email": "lighting@civiclens.gov.in"
    },
    {
        "code": "SANITATION",
        "name": "Solid Waste Management & Sanitation",
        "description": "Responsible for garbage dumping, public hygiene, and litter removal.",
        "contact_email": "sanitation@civiclens.gov.in"
    },
    {
        "code": "PUBLIC_WORKS",
        "name": "Public Works & Infrastructure",
        "description": "Responsible for footpaths, bridges, guard rails, and public structures.",
        "contact_email": "pwd@civiclens.gov.in"
    }
]

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@(?:[\w\-]+\.)+[a-zA-Z]{2,}$")
CODE_REGEX = re.compile(r"^[A-Z0-9_]{2,30}$")


class DepartmentManagementService:
    """Manages municipal departments, rosters, and officer assignments."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def seed_default_departments(self) -> int:
        """Ensures core municipal departments and default municipality exist in the database."""
        db: Session = self._session_factory()
        created_count = 0
        try:
            # Ensure default municipality exists
            muni = db.query(Municipality).filter_by(code="BBMP").first()
            if not muni:
                muni = Municipality(
                    id="9951f5f4-8ada-4604-b714-054794edeccd",
                    name="Bruhat Bengaluru Mahanagara Palike",
                    code="BBMP",
                    state="Karnataka",
                    status="active",
                )
                db.add(muni)
                db.flush()

            for dept_spec in DEFAULT_DEPARTMENTS:
                existing = db.query(Department).filter(
                    (Department.code == dept_spec["code"]) | (Department.name == dept_spec["name"])
                ).first()
                if not existing:
                    dept = Department(
                        id=str(uuid.uuid4()),
                        municipality_id=muni.id,
                        name=dept_spec["name"],
                        code=dept_spec["code"],
                        description=dept_spec["description"],
                        contact_email=dept_spec.get("contact_email"),
                        is_active=True,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    db.add(dept)
                    created_count += 1
                else:
                    if not existing.municipality_id:
                        existing.municipality_id = muni.id
                    if not existing.code:
                        existing.code = dept_spec["code"]
                    existing.updated_at = datetime.now(timezone.utc)
            db.commit()
            return created_count
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_departments(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Lists all municipal departments with live incident and officer workload counts."""
        db: Session = self._session_factory()
        try:
            query = db.query(Department)
            if not include_inactive:
                query = query.filter_by(is_active=True)

            departments = query.order_by(Department.name.asc()).all()
            results = []
            for d in departments:
                # Count open incidents
                open_incidents = db.query(func.count(Incident.id)).filter(
                    Incident.department_id == d.id,
                    ~Incident.status.in_(["resolved", "closed", "rejected"])
                ).scalar() or 0

                # Count active members
                member_count = db.query(func.count(DepartmentMembership.id)).filter(
                    DepartmentMembership.department_id == d.id,
                    DepartmentMembership.is_active == True
                ).scalar() or 0

                results.append({
                    "id": d.id,
                    "code": d.code,
                    "name": d.name,
                    "description": d.description,
                    "contact_email": d.contact_email,
                    "contact_phone": d.contact_phone,
                    "is_active": d.is_active,
                    "open_incidents_count": open_incidents,
                    "officers_count": member_count,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "updated_at": d.updated_at.isoformat() if d.updated_at else None
                })
            return results
        finally:
            db.close()

    def get_department(self, dept_id: str) -> Dict[str, Any]:
        """Retrieves single department with detailed officer roster."""
        db: Session = self._session_factory()
        try:
            dept = db.query(Department).filter_by(id=dept_id).first()
            if not dept:
                raise NotFoundError(f"Department '{dept_id}' not found.")

            memberships = db.query(DepartmentMembership, User).join(
                User, DepartmentMembership.user_id == User.id
            ).filter(
                DepartmentMembership.department_id == dept.id,
                DepartmentMembership.is_active == True
            ).all()

            roster = []
            for m, u in memberships:
                assigned_count = db.query(func.count(Incident.id)).filter(
                    Incident.assigned_officer_id == u.id,
                    ~Incident.status.in_(["resolved", "closed", "rejected"])
                ).scalar() or 0

                roster.append({
                    "user_id": u.id,
                    "display_name": u.display_name,
                    "email": u.email,
                    "role": u.role,
                    "role_in_dept": m.role_in_dept,
                    "joined_at": m.joined_at.isoformat() if m.joined_at else None,
                    "active_incidents": assigned_count
                })

            open_incidents = db.query(func.count(Incident.id)).filter(
                Incident.department_id == dept.id,
                ~Incident.status.in_(["resolved", "closed", "rejected"])
            ).scalar() or 0

            return {
                "id": dept.id,
                "code": dept.code,
                "name": dept.name,
                "description": dept.description,
                "contact_email": dept.contact_email,
                "contact_phone": dept.contact_phone,
                "is_active": dept.is_active,
                "open_incidents_count": open_incidents,
                "roster": roster,
                "created_at": dept.created_at.isoformat() if dept.created_at else None
            }
        finally:
            db.close()

    def create_department(
        self,
        name: str,
        code: str,
        description: Optional[str] = None,
        contact_email: Optional[str] = None,
        contact_phone: Optional[str] = None,
        actor_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new municipal department with code uniqueness validation."""
        if not name or len(name.strip()) < 3:
            raise ValidationError("Department name must be at least 3 characters.")
        name = name.strip()

        if not code or not CODE_REGEX.match(code.strip().upper()):
            raise ValidationError("Department code must be 2-30 uppercase alphanumeric characters or underscores (e.g., 'ROAD_MAINT').")
        code = code.strip().upper()

        if contact_email and not EMAIL_REGEX.match(contact_email.strip()):
            raise ValidationError("Invalid contact email address.")

        db: Session = self._session_factory()
        try:
            # Check unique code & name
            dup = db.query(Department).filter(
                (Department.code == code) | (Department.name == name)
            ).first()
            if dup:
                raise ValidationError(f"A department with code '{code}' or name '{name}' already exists.")

            dept = Department(
                id=str(uuid.uuid4()),
                name=name,
                code=code,
                description=description.strip() if description else None,
                contact_email=contact_email.strip() if contact_email else None,
                contact_phone=contact_phone.strip() if contact_phone else None,
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            db.add(dept)

            if actor_id:
                audit = AuditLog(
                    id=str(uuid.uuid4()),
                    actor_id=actor_id,
                    action="create_department",
                    entity_type="department",
                    entity_id=dept.id,
                    details=json.dumps({"code": code, "name": name}),
                    created_at=datetime.now(timezone.utc)
                )
                db.add(audit)

            db.commit()
            return {
                "id": dept.id,
                "code": dept.code,
                "name": dept.name,
                "description": dept.description,
                "is_active": dept.is_active,
                "created_at": dept.created_at.isoformat()
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def update_department(
        self,
        dept_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        contact_email: Optional[str] = None,
        contact_phone: Optional[str] = None,
        is_active: Optional[bool] = None,
        actor_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Updates department details with deactivation guards."""
        db: Session = self._session_factory()
        try:
            dept = db.query(Department).filter_by(id=dept_id).first()
            if not dept:
                raise NotFoundError(f"Department '{dept_id}' not found.")

            if name is not None:
                if len(name.strip()) < 3:
                    raise ValidationError("Department name must be at least 3 characters.")
                dept.name = name.strip()

            if description is not None:
                dept.description = description.strip()
            if contact_email is not None:
                if contact_email.strip() and not EMAIL_REGEX.match(contact_email.strip()):
                    raise ValidationError("Invalid contact email address.")
                dept.contact_email = contact_email.strip() if contact_email.strip() else None
            if contact_phone is not None:
                dept.contact_phone = contact_phone.strip() if contact_phone.strip() else None

            # Guard deactivation if active unresolved incidents exist
            if is_active is False and dept.is_active is True:
                open_count = db.query(func.count(Incident.id)).filter(
                    Incident.department_id == dept.id,
                    ~Incident.status.in_(["resolved", "closed", "rejected"])
                ).scalar() or 0
                if open_count > 0:
                    raise ValidationError(
                        f"Cannot deactivate department '{dept.name}' while it has {open_count} active unresolved incidents. Please reassign them first."
                    )
                dept.is_active = False
            elif is_active is True:
                dept.is_active = True

            dept.updated_at = datetime.now(timezone.utc)

            if actor_id:
                audit = AuditLog(
                    id=str(uuid.uuid4()),
                    actor_id=actor_id,
                    action="update_department",
                    entity_type="department",
                    entity_id=dept.id,
                    details=json.dumps({"is_active": dept.is_active}),
                    created_at=datetime.now(timezone.utc)
                )
                db.add(audit)

            db.commit()
            return {
                "id": dept.id,
                "code": dept.code,
                "name": dept.name,
                "description": dept.description,
                "is_active": dept.is_active,
                "updated_at": dept.updated_at.isoformat()
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def onboard_officer(
        self,
        display_name: str,
        email: str,
        password: str,
        role: str,
        department_id: Optional[str] = None,
        role_in_dept: str = "officer",
        actor_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Onboards a municipal officer, dept admin, or municipal admin."""
        valid_roles = {"municipal_officer", "dept_admin", "municipal_admin", "system_admin"}
        if role not in valid_roles:
            raise ValidationError(f"Invalid municipal role '{role}'. Allowed: {sorted(valid_roles)}")

        if not display_name or len(display_name.strip()) < 2:
            raise ValidationError("Full name is required and must be at least 2 characters.")
        display_name = display_name.strip()

        if not email or not EMAIL_REGEX.match(email.strip()):
            raise ValidationError("Valid official email address is required.")
        email = email.strip().lower()

        if not password or len(password) < 8:
            raise ValidationError("Password must be at least 8 characters.")

        db: Session = self._session_factory()
        try:
            # Validate department if provided
            dept = None
            if department_id:
                dept = db.query(Department).filter_by(id=department_id, is_active=True).first()
                if not dept:
                    raise NotFoundError(f"Active department '{department_id}' not found.")

            # Check existing email
            existing_user = db.query(User).filter_by(email=email).first()
            if existing_user:
                # Update existing official or elevate citizen to municipal official role
                existing_user.role = role
                existing_user.display_name = display_name
                if password:
                    existing_user.password_hash = generate_password_hash(password)
                existing_user.is_active = True
                user = existing_user
            else:
                user = User(
                    id=str(uuid.uuid4()),
                    display_name=display_name,
                    email=email,
                    role=role,
                    password_hash=generate_password_hash(password),
                    is_active=True,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(user)

            # Assign membership if department provided
            if dept:
                existing_mem = db.query(DepartmentMembership).filter_by(
                    user_id=user.id,
                    department_id=dept.id
                ).first()
                if existing_mem:
                    existing_mem.is_active = True
                    existing_mem.role_in_dept = role_in_dept if role_in_dept in {"officer", "lead", "admin"} else "officer"
                else:
                    membership = DepartmentMembership(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        department_id=dept.id,
                        role_in_dept=role_in_dept if role_in_dept in {"officer", "lead", "admin"} else "officer",
                        is_active=True,
                        joined_at=datetime.now(timezone.utc)
                    )
                    db.add(membership)

            if actor_id:
                audit = AuditLog(
                    id=str(uuid.uuid4()),
                    actor_id=actor_id,
                    action="onboard_officer",
                    entity_type="user",
                    entity_id=user.id,
                    details=json.dumps({
                        "email": email,
                        "role": role,
                        "department_id": department_id
                    }),
                    created_at=datetime.now(timezone.utc)
                )
                db.add(audit)

            db.commit()
            return {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
                "role": user.role,
                "department_id": dept.id if dept else None,
                "department_name": dept.name if dept else None,
                "created_at": user.created_at.isoformat()
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_officers(self, department_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists municipal officers with current workload metrics."""
        db: Session = self._session_factory()
        try:
            query = db.query(User).filter(
                User.role.in_(["municipal_officer", "dept_admin", "municipal_admin"]),
                User.is_active == True
            )

            officers = query.order_by(User.display_name.asc()).all()
            results = []
            for u in officers:
                # Find active memberships
                memberships = db.query(DepartmentMembership, Department).join(
                    Department, DepartmentMembership.department_id == Department.id
                ).filter(
                    DepartmentMembership.user_id == u.id,
                    DepartmentMembership.is_active == True
                ).all()

                dept_list = [{
                    "department_id": d.id,
                    "code": d.code,
                    "name": d.name,
                    "role_in_dept": m.role_in_dept
                } for m, d in memberships]

                # Filter if department_id is requested
                if department_id and not any(d["department_id"] == department_id for d in dept_list):
                    continue

                active_tasks = db.query(func.count(Incident.id)).filter(
                    Incident.assigned_officer_id == u.id,
                    ~Incident.status.in_(["resolved", "closed", "rejected"])
                ).scalar() or 0

                resolved_tasks = db.query(func.count(Incident.id)).filter(
                    Incident.assigned_officer_id == u.id,
                    Incident.status.in_(["resolved", "closed"])
                ).scalar() or 0

                results.append({
                    "id": u.id,
                    "display_name": u.display_name,
                    "email": u.email,
                    "role": u.role,
                    "departments": dept_list,
                    "active_incidents_count": active_tasks,
                    "resolved_incidents_count": resolved_tasks,
                    "created_at": u.created_at.isoformat() if u.created_at else None
                })
            return results
        finally:
            db.close()
