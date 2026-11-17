"""
Showcase Repository
===================
Data access layer for CivicLens Homepage Impact Showcase items.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, and_, or_

from backend.db.models import HomepageShowcaseItem, EvidenceAsset, Incident


class ShowcaseRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, item_id: str) -> Optional[HomepageShowcaseItem]:
        return self.session.query(HomepageShowcaseItem).filter_by(id=item_id).first()

    def get_public_showcase_items(
        self,
        category: Optional[str] = None,
        before_after_type: Optional[str] = None,
        featured_only: bool = False,
        limit: int = 20,
    ) -> List[HomepageShowcaseItem]:
        """Returns only approved, published showcase items within active date windows."""
        now = datetime.now(timezone.utc)
        q = self.session.query(HomepageShowcaseItem).filter(
            HomepageShowcaseItem.publication_status == "PUBLISHED",
            HomepageShowcaseItem.moderation_status == "APPROVED",
        )
        # Date checks
        q = q.filter(
            or_(HomepageShowcaseItem.starts_at.is_(None), HomepageShowcaseItem.starts_at <= now),
            or_(HomepageShowcaseItem.ends_at.is_(None), HomepageShowcaseItem.ends_at >= now),
        )
        if category and category != "all":
            q = q.filter(HomepageShowcaseItem.category == category)
        if before_after_type:
            q = q.filter(HomepageShowcaseItem.before_after_type == before_after_type)
        if featured_only:
            q = q.filter(HomepageShowcaseItem.is_featured.is_(True))

        return q.order_by(
            HomepageShowcaseItem.is_featured.desc(),
            HomepageShowcaseItem.sort_order.asc(),
            HomepageShowcaseItem.created_at.desc(),
        ).limit(limit).all()

    def list_all_items(
        self,
        publication_status: Optional[str] = None,
        moderation_status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[HomepageShowcaseItem]:
        """List items for municipal management portal."""
        q = self.session.query(HomepageShowcaseItem)
        if publication_status:
            q = q.filter(HomepageShowcaseItem.publication_status == publication_status)
        if moderation_status:
            q = q.filter(HomepageShowcaseItem.moderation_status == moderation_status)
        if category:
            q = q.filter(HomepageShowcaseItem.category == category)
        return q.order_by(HomepageShowcaseItem.created_at.desc()).offset(offset).limit(limit).all()

    def count_items(
        self,
        publication_status: Optional[str] = None,
        moderation_status: Optional[str] = None,
    ) -> int:
        q = self.session.query(HomepageShowcaseItem)
        if publication_status:
            q = q.filter(HomepageShowcaseItem.publication_status == publication_status)
        if moderation_status:
            q = q.filter(HomepageShowcaseItem.moderation_status == moderation_status)
        return q.count()

    def create(self, item: HomepageShowcaseItem) -> HomepageShowcaseItem:
        self.session.add(item)
        self.session.commit()
        return item

    def update(self, item: HomepageShowcaseItem) -> HomepageShowcaseItem:
        item.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        return item

    def delete(self, item_id: str) -> bool:
        item = self.get_by_id(item_id)
        if not item:
            return False
        self.session.delete(item)
        self.session.commit()
        return True
