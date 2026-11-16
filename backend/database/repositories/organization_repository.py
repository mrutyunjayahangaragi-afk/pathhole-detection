"""
Organization Repository
=======================
Data access layer for Municipalities, Departments, and Department Memberships.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from backend.db.models import Municipality, Department, DepartmentMembership


class OrganizationRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_municipalities(self, status: str = "active") -> List[Municipality]:
        """Lists active municipalities."""
        return self.session.query(Municipality).filter_by(status=status).order_by(Municipality.name).all()

    def get_municipality_by_id(self, municipality_id: str) -> Optional[Municipality]:
        """Gets a municipality by its UUID."""
        return self.session.query(Municipality).filter_by(id=municipality_id).first()

    def get_municipality_by_code(self, code: str) -> Optional[Municipality]:
        """Gets a municipality by its unique code (e.g. BBMP)."""
        return self.session.query(Municipality).filter_by(code=code.strip().upper()).first()

    def list_departments(self, municipality_id: Optional[str] = None) -> List[Department]:
        """Lists active departments, optionally filtered by municipality."""
        query = self.session.query(Department).filter_by(is_active=True)
        if municipality_id:
            query = query.filter_by(municipality_id=municipality_id)
        return query.order_by(Department.name).all()

    def get_department_by_id(self, department_id: str) -> Optional[Department]:
        """Gets a department by its UUID."""
        return self.session.query(Department).filter_by(id=department_id, is_active=True).first()

    def get_department_by_code(self, code: str) -> Optional[Department]:
        """Gets a department by its code (e.g. ROAD_MAINT)."""
        return self.session.query(Department).filter_by(code=code.strip().upper(), is_active=True).first()

    def get_user_memberships(self, user_id: str) -> List[DepartmentMembership]:
        """Gets all active department memberships for a user."""
        return self.session.query(DepartmentMembership).filter_by(
            user_id=user_id, is_active=True
        ).all()
