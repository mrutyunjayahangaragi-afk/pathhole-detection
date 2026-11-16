"""multilingual_and_location_schema

Revision ID: e6b19a73d914
Revises: c5a91f42e873
Create Date: 2026-11-16 12:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6b19a73d914'
down_revision: Union[str, None] = 'c5a91f42e873'
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
    # 1. Extended language metadata on citizen_reports_v2
    if not _column_exists('citizen_reports_v2', 'detected_language'):
        op.add_column('citizen_reports_v2', sa.Column('detected_language', sa.String(length=10), nullable=True))
    if not _column_exists('citizen_reports_v2', 'language_detection_confidence'):
        op.add_column('citizen_reports_v2', sa.Column('language_detection_confidence', sa.Float(), nullable=True))
    if not _column_exists('citizen_reports_v2', 'language_detection_model'):
        op.add_column('citizen_reports_v2', sa.Column('language_detection_model', sa.String(length=50), nullable=True))
    if not _column_exists('citizen_reports_v2', 'language_detection_status'):
        op.add_column('citizen_reports_v2', sa.Column('language_detection_status', sa.String(length=30), server_default='pending', nullable=False))

    # 2. Table: report_translations
    if not _table_exists('report_translations'):
        op.create_table(
            'report_translations',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('report_id', sa.String(length=36), sa.ForeignKey('citizen_reports_v2.id', ondelete='CASCADE'), nullable=False),
            sa.Column('report_item_id', sa.String(length=36), sa.ForeignKey('report_items.id', ondelete='SET NULL'), nullable=True),
            sa.Column('source_language', sa.String(length=10), nullable=False),
            sa.Column('target_language', sa.String(length=10), nullable=False),
            sa.Column('original_text', sa.Text(), nullable=False),
            sa.Column('translated_text', sa.Text(), nullable=True),
            sa.Column('provider_name', sa.String(length=50), nullable=False, server_default='civic_rule_dict'),
            sa.Column('model_name', sa.String(length=100), nullable=True),
            sa.Column('model_version', sa.String(length=50), nullable=True),
            sa.Column('translation_status', sa.String(length=30), nullable=False, server_default='COMPLETED'),
            sa.Column('review_status', sa.String(length=30), nullable=False, server_default='unreviewed'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "translation_status IN ('NOT_REQUESTED','PENDING','PROCESSING','COMPLETED','FAILED','NEEDS_REVIEW')",
                name='ck_trans_status'
            ),
            sa.CheckConstraint(
                "review_status IN ('unreviewed','verified','corrected')",
                name='ck_trans_review'
            ),
        )
        try:
            op.create_index('ix_trans_report', 'report_translations', ['report_id'], unique=False)
            op.create_index('ix_trans_status', 'report_translations', ['translation_status'], unique=False)
        except Exception:
            pass

    # 3. Table: ai_description_assistance
    if not _table_exists('ai_description_assistance'):
        op.create_table(
            'ai_description_assistance',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('report_id', sa.String(length=36), sa.ForeignKey('citizen_reports_v2.id', ondelete='CASCADE'), nullable=False),
            sa.Column('report_item_id', sa.String(length=36), sa.ForeignKey('report_items.id', ondelete='SET NULL'), nullable=True),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column('suggested_category', sa.String(length=50), nullable=True),
            sa.Column('missing_info_flags', sa.Text(), nullable=True),
            sa.Column('output_language', sa.String(length=10), nullable=False, server_default='en'),
            sa.Column('provider_name', sa.String(length=50), nullable=False, server_default='civic_rule_assist'),
            sa.Column('model_name', sa.String(length=100), nullable=True),
            sa.Column('model_version', sa.String(length=50), nullable=True),
            sa.Column('processing_status', sa.String(length=30), nullable=False, server_default='completed'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        try:
            op.create_index('ix_ai_assist_report', 'ai_description_assistance', ['report_id'], unique=False)
        except Exception:
            pass

    # 4. Table: location_records
    if not _table_exists('location_records'):
        op.create_table(
            'location_records',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('report_id', sa.String(length=36), sa.ForeignKey('citizen_reports_v2.id', ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column('latitude', sa.Float(), nullable=False),
            sa.Column('longitude', sa.Float(), nullable=False),
            sa.Column('location_accuracy_m', sa.Float(), nullable=True),
            sa.Column('location_source', sa.String(length=30), nullable=False, server_default='manual_pin'),
            sa.Column('road_name', sa.String(length=255), nullable=True),
            sa.Column('road_type', sa.String(length=50), nullable=True),
            sa.Column('locality', sa.String(length=255), nullable=True),
            sa.Column('suburb', sa.String(length=255), nullable=True),
            sa.Column('city', sa.String(length=255), nullable=True),
            sa.Column('district', sa.String(length=255), nullable=True),
            sa.Column('state', sa.String(length=255), nullable=True),
            sa.Column('postal_code', sa.String(length=20), nullable=True),
            sa.Column('country', sa.String(length=100), nullable=True),
            sa.Column('normalized_address', sa.Text(), nullable=True),
            sa.Column('raw_geocoding_json', sa.Text(), nullable=True),
            sa.Column('geocoding_provider', sa.String(length=50), nullable=False, server_default='nominatim'),
            sa.Column('geocoding_status', sa.String(length=30), nullable=False, server_default='pending'),
            sa.Column('geocoded_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "location_source IN ('device_gps','manual_pin','exif_gps','citizen_text')",
                name='ck_loc_source'
            ),
        )
        try:
            op.create_index('ix_loc_records_coords', 'location_records', ['latitude', 'longitude'], unique=False)
        except Exception:
            pass


def downgrade() -> None:
    if _table_exists('location_records'):
        op.drop_table('location_records')
    if _table_exists('ai_description_assistance'):
        op.drop_table('ai_description_assistance')
    if _table_exists('report_translations'):
        op.drop_table('report_translations')
    if _column_exists('citizen_reports_v2', 'language_detection_status'):
        op.drop_column('citizen_reports_v2', 'language_detection_status')
    if _column_exists('citizen_reports_v2', 'language_detection_model'):
        op.drop_column('citizen_reports_v2', 'language_detection_model')
    if _column_exists('citizen_reports_v2', 'language_detection_confidence'):
        op.drop_column('citizen_reports_v2', 'language_detection_confidence')
    if _column_exists('citizen_reports_v2', 'detected_language'):
        op.drop_column('citizen_reports_v2', 'detected_language')
