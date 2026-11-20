"""
CivicLens Department Routing Service
====================================
Maps citizen complaint defect categories to authoritative municipal departments
using standardized department unit codes and dynamic database lookup.
Never hardcodes database IDs.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.db.engine import get_session_factory
from backend.db.models import Department

logger = logging.getLogger("civiclens.routing")

# Canonical mapping of category keywords to Department unit codes
CATEGORY_DEPARTMENT_CODE_MAP: Dict[str, str] = {
    # Road & Highway Maintenance
    "pothole": "ROAD_MAINT",
    "road_damage": "ROAD_MAINT",
    "potholes": "ROAD_MAINT",
    "asphalt_crack": "ROAD_MAINT",
    "manhole": "ROAD_MAINT",

    # Electrical & Streetlighting
    "broken_streetlight": "STREETLIGHT",
    "streetlight": "STREETLIGHT",
    "streetlights": "STREETLIGHT",
    "lighting": "STREETLIGHT",
    "electrical_pole": "STREETLIGHT",
    "dark_street": "STREETLIGHT",

    # Solid Waste Management
    "solid_waste": "SOLID_WASTE",
    "garbage": "SOLID_WASTE",
    "sanitation": "SOLID_WASTE",
    "waste_dumping": "SOLID_WASTE",
    "overflowing_bin": "SOLID_WASTE",

    # Stormwater & Drainage
    "drainage": "DRAINAGE",
    "waterlogging": "DRAINAGE",
    "stormwater": "DRAINAGE",
    "blocked_drain": "DRAINAGE",
    "flood": "DRAINAGE",

    # Water Supply & Sewerage Board
    "water_leakage": "BWSSB",
    "water_leak": "BWSSB",
    "pipe_burst": "BWSSB",
    "sewerage": "BWSSB",
    "sewage_overflow": "BWSSB",

    # Traffic Engineering & Signals
    "traffic_signal": "TRAFFIC_ENG",
    "broken_signal": "TRAFFIC_ENG",
    "road_sign": "TRAFFIC_ENG",
    "missing_sign": "TRAFFIC_ENG",
    "speed_breaker": "TRAFFIC_ENG",

    # Pedestrian Walkways & Footpaths
    "footpaths": "FOOTPATHS",
    "footpath": "FOOTPATHS",
    "sidewalk": "FOOTPATHS",
    "broken_paver": "FOOTPATHS",
    "encroachment": "FOOTPATHS",

    # Public Works & Infrastructure
    "bridge_damage": "PUBLIC_WORKS",
    "flyover_crack": "PUBLIC_WORKS",
    "retaining_wall": "PUBLIC_WORKS",
    "public_infrastructure": "PUBLIC_WORKS",
    "other": "PUBLIC_WORKS",
}

DEFAULT_DEPARTMENT_CODE = "ROAD_MAINT"


class DepartmentRoutingService:
    """Resolves the responsible municipal department for any complaint category."""

    def __init__(self, session_factory=None):
        self._custom_session_factory = session_factory

    @property
    def _session_factory(self):
        return self._custom_session_factory or get_session_factory()

    def resolve_department_code(self, category: str) -> str:
        """Normalizes defect category and returns target department unit code."""
        if not category:
            return DEFAULT_DEPARTMENT_CODE
        normalized = category.strip().lower().replace(" ", "_").replace("-", "_")
        return CATEGORY_DEPARTMENT_CODE_MAP.get(normalized, DEFAULT_DEPARTMENT_CODE)

    def resolve_department(self, category: str, db: Optional[Session] = None) -> Optional[Department]:
        """
        Dynamically retrieves the active Department record from the database.
        Never relies on hardcoded primary keys.
        """
        code = self.resolve_department_code(category)
        owns_session = db is None
        session: Session = db if db is not None else self._session_factory()

        try:
            dept = session.query(Department).filter(
                Department.code == code,
                Department.is_active == True
            ).first()

            if not dept:
                # Fallback to ROAD_MAINT or any active department
                dept = session.query(Department).filter(
                    Department.code == DEFAULT_DEPARTMENT_CODE,
                    Department.is_active == True
                ).first()

            if not dept:
                dept = session.query(Department).filter(Department.is_active == True).first()

            return dept
        except Exception as e:
            logger.error(f"Error resolving department for category '{category}': {e}")
            return None
        finally:
            if owns_session:
                session.close()

    @staticmethod
    def get_supported_categories() -> Dict[str, str]:
        """Returns map of supported categories to department unit codes."""
        return dict(CATEGORY_DEPARTMENT_CODE_MAP)
