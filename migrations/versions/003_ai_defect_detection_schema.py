"""ai_defect_detection_schema

Revision ID: b4f8c291d325
Revises: a3e7b198c214
Create Date: 2026-11-16 00:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4f8c291d325'
down_revision: Union[str, None] = 'a3e7b198c214'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Detection runs metadata
    op.add_column('detection_runs', sa.Column('processing_duration_ms', sa.Float(), nullable=True))
    op.add_column('detection_runs', sa.Column('error_code', sa.String(length=50), nullable=True))
    op.add_column('detection_runs', sa.Column('error_message', sa.Text(), nullable=True))

    # 2. Detections multi-object & normalized coordinates
    op.add_column('detections_v3', sa.Column('evidence_asset_id', sa.String(length=36), nullable=True))
    op.add_column('detections_v3', sa.Column('confidence_tier', sa.String(length=20), server_default='medium', nullable=True))
    op.add_column('detections_v3', sa.Column('normalized_xmin', sa.Float(), nullable=True))
    op.add_column('detections_v3', sa.Column('normalized_ymin', sa.Float(), nullable=True))
    op.add_column('detections_v3', sa.Column('normalized_xmax', sa.Float(), nullable=True))
    op.add_column('detections_v3', sa.Column('normalized_ymax', sa.Float(), nullable=True))
    op.add_column('detections_v3', sa.Column('image_width', sa.Integer(), nullable=True))
    op.add_column('detections_v3', sa.Column('image_height', sa.Integer(), nullable=True))
    op.add_column('detections_v3', sa.Column('reviewed_by', sa.String(length=36), nullable=True))
    op.add_column('detections_v3', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('detections_v3', sa.Column('review_notes', sa.Text(), nullable=True))

    # Index for fast lookup of detections by evidence asset
    try:
        op.create_index('ix_detections_v3_evidence', 'detections_v3', ['evidence_asset_id'], unique=False)
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_index('ix_detections_v3_evidence', table_name='detections_v3')
    except Exception:
        pass

    op.drop_column('detections_v3', 'review_notes')
    op.drop_column('detections_v3', 'reviewed_at')
    op.drop_column('detections_v3', 'reviewed_by')
    op.drop_column('detections_v3', 'image_height')
    op.drop_column('detections_v3', 'image_width')
    op.drop_column('detections_v3', 'normalized_ymax')
    op.drop_column('detections_v3', 'normalized_xmax')
    op.drop_column('detections_v3', 'normalized_ymin')
    op.drop_column('detections_v3', 'normalized_xmin')
    op.drop_column('detections_v3', 'confidence_tier')
    op.drop_column('detections_v3', 'evidence_asset_id')

    op.drop_column('detection_runs', 'error_message')
    op.drop_column('detection_runs', 'error_code')
    op.drop_column('detection_runs', 'processing_duration_ms')
