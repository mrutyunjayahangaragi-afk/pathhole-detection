"""duplicate_matching_schema

Revision ID: c5a91f42e873
Revises: b4f8c291d325
Create Date: 2026-11-16 11:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5a91f42e873'
down_revision: Union[str, None] = 'b4f8c291d325'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table_name in insp.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # 1. Evidence visual features on evidence_assets_v2
    if not _column_exists('evidence_assets_v2', 'perceptual_hash'):
        op.add_column('evidence_assets_v2', sa.Column('perceptual_hash', sa.String(length=64), nullable=True))
    if not _column_exists('evidence_assets_v2', 'hash_algorithm'):
        op.add_column('evidence_assets_v2', sa.Column('hash_algorithm', sa.String(length=30), server_default='dct_phash', nullable=True))
    if not _column_exists('evidence_assets_v2', 'hash_version'):
        op.add_column('evidence_assets_v2', sa.Column('hash_version', sa.String(length=20), server_default='v1.0', nullable=True))
    try:
        op.create_index('ix_evidence_phash', 'evidence_assets_v2', ['perceptual_hash'], unique=False)
    except Exception:
        pass

    # 2. Detection crop embeddings
    if not _table_exists('detection_embeddings'):
        op.create_table(
            'detection_embeddings',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('detection_id', sa.String(length=36), sa.ForeignKey('detections_v3.id', ondelete='CASCADE'), nullable=True),
            sa.Column('evidence_asset_id', sa.String(length=36), sa.ForeignKey('evidence_assets_v2.id', ondelete='CASCADE'), nullable=True),
            sa.Column('crop_bbox_json', sa.Text(), nullable=True),
            sa.Column('embedding_vector', sa.JSON(), nullable=True),
            sa.Column('embedding_model', sa.String(length=100), nullable=False, server_default='mock_embedding'),
            sa.Column('embedding_model_version', sa.String(length=50), nullable=False, server_default='v1.0'),
            sa.Column('embedding_dimension', sa.Integer(), nullable=False, server_default='128'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        try:
            op.create_index('ix_detection_embeddings_det', 'detection_embeddings', ['detection_id'], unique=False)
            op.create_index('ix_detection_embeddings_asset', 'detection_embeddings', ['evidence_asset_id'], unique=False)
        except Exception:
            pass

    # 3. Match evaluations
    if not _table_exists('match_evaluations'):
        op.create_table(
            'match_evaluations',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('report_item_id', sa.String(length=36), sa.ForeignKey('report_items.id', ondelete='CASCADE'), nullable=False),
            sa.Column('matching_algorithm_version', sa.String(length=50), nullable=False, server_default='v1.0.0'),
            sa.Column('processing_status', sa.String(length=20), nullable=False, server_default='completed'),
            sa.Column('overall_decision', sa.String(length=30), nullable=False),
            sa.Column('candidate_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('top_score', sa.Float(), nullable=True),
            sa.Column('configuration_version', sa.String(length=50), nullable=False, server_default='v1.0'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        )
        try:
            op.create_index('ix_match_eval_item', 'match_evaluations', ['report_item_id'], unique=False)
        except Exception:
            pass

    # 4. Match candidates
    if not _table_exists('match_candidates'):
        op.create_table(
            'match_candidates',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('match_evaluation_id', sa.String(length=36), sa.ForeignKey('match_evaluations.id', ondelete='CASCADE'), nullable=False),
            sa.Column('candidate_incident_id', sa.String(length=36), sa.ForeignKey('incidents_v2.id', ondelete='CASCADE'), nullable=False),
            sa.Column('candidate_rank', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('combined_score', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('geographic_distance_m', sa.Float(), nullable=True),
            sa.Column('geographic_score', sa.Float(), nullable=True),
            sa.Column('visual_similarity_score', sa.Float(), nullable=True),
            sa.Column('perceptual_similarity_score', sa.Float(), nullable=True),
            sa.Column('exact_match_signal', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('category_score', sa.Float(), nullable=True),
            sa.Column('text_score', sa.Float(), nullable=True),
            sa.Column('decision_reason', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        try:
            op.create_index('ix_match_candidates_eval', 'match_candidates', ['match_evaluation_id'], unique=False)
            op.create_index('ix_match_candidates_incident', 'match_candidates', ['candidate_incident_id'], unique=False)
        except Exception:
            pass

    # 5. Match decisions extension
    if not _column_exists('match_decisions_v2', 'match_evaluation_id'):
        op.add_column('match_decisions_v2', sa.Column('match_evaluation_id', sa.String(length=36), nullable=True))
    if not _column_exists('match_decisions_v2', 'decision_source'):
        op.add_column('match_decisions_v2', sa.Column('decision_source', sa.String(length=30), server_default='human_reviewer', nullable=True))
    if not _column_exists('match_decisions_v2', 'notes'):
        op.add_column('match_decisions_v2', sa.Column('notes', sa.Text(), nullable=True))

    # 6. Incident consolidations history
    if not _table_exists('incident_consolidations'):
        op.create_table(
            'incident_consolidations',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('canonical_incident_id', sa.String(length=36), sa.ForeignKey('incidents_v2.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('superseded_incident_id', sa.String(length=36), sa.ForeignKey('incidents_v2.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('consolidated_by', sa.String(length=36), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('consolidation_reason', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        try:
            op.create_index('ix_consolidation_canonical', 'incident_consolidations', ['canonical_incident_id'], unique=False)
            op.create_index('ix_consolidation_superseded', 'incident_consolidations', ['superseded_incident_id'], unique=False)
        except Exception:
            pass


def downgrade() -> None:
    try:
        op.drop_table('incident_consolidations')
    except Exception:
        pass

    try:
        op.drop_column('match_decisions_v2', 'notes')
        op.drop_column('match_decisions_v2', 'decision_source')
        op.drop_column('match_decisions_v2', 'match_evaluation_id')
    except Exception:
        pass

    try:
        op.drop_table('match_candidates')
    except Exception:
        pass

    try:
        op.drop_table('match_evaluations')
    except Exception:
        pass

    try:
        op.drop_table('detection_embeddings')
    except Exception:
        pass

    try:
        op.drop_index('ix_evidence_phash', table_name='evidence_assets_v2')
    except Exception:
        pass

    try:
        op.drop_column('evidence_assets_v2', 'hash_version')
        op.drop_column('evidence_assets_v2', 'hash_algorithm')
        op.drop_column('evidence_assets_v2', 'perceptual_hash')
    except Exception:
        pass
