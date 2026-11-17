"""
Department Repository
=====================
Persistence operations for municipal departments and officer memberships.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.db.models import Department, DepartmentMembership


class DepartmentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_departments(self, municipality_id: Optional[str] = None) -> List[Department]:
        """Retrieves all active departments, optionally scoped to a municipality."""
        query = self.session.query(Department).filter(Department.is_active.is_(True))
        if municipality_id:
            query = query.filter(Department.municipality_id == municipality_id)
        return query.order_by(Department.name.asc()).all()

    def get_by_id(self, department_id: str) -> Optional[Department]:
        """Retrieves a department by its primary UUID."""
        return self.session.query(Department).filter_by(id=department_id).first()

    def get_by_code(self, code: str) -> Optional[Department]:
        """Retrieves a department by its unique code (e.g. BBMP-RDS)."""
        return self.session.query(Department).filter_by(code=code).first()

    def get_department_members(self, department_id: str) -> List[DepartmentMembership]:
        """Retrieves official staff memberships assigned to a department."""
        return (
            self.session.query(DepartmentMembership)
            .filter_by(department_id=department_id)
            .all()
        )

    def add_member(self, data: Dict[str, Any]) -> DepartmentMembership:
        """Assigns an official user to a municipal department."""
        membership = DepartmentMembership(**data)
        self.session.add(membership)
        self.session.flush()
        return membership
