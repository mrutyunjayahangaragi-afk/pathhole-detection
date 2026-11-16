"""municipal_workflow_schema

Revision ID: f7c20a84e025
Revises: e6b19a73d914
Create Date: 2026-11-16 12:54:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c20a84e025'
down_revision: Union[str, None] = 'e6b19a73d914'
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
    # 1. Extended fields on departments
    if not _column_exists('departments', 'code'):
        op.add_column('departments', sa.Column('code', sa.String(length=50), nullable=True))
    if not _column_exists('departments', 'updated_at'):
        op.add_column('departments', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
    try:
        op.create_index('ix_departments_code', 'departments', ['code'], unique=True)
    except Exception:
        pass

    # 2. Extended fields on incidents_v2
    if not _column_exists('incidents_v2', 'priority'):
        op.add_column('incidents_v2', sa.Column('priority', sa.String(length=10), server_default='normal', nullable=False))
    if not _column_exists('incidents_v2', 'department_id'):
        op.add_column('incidents_v2', sa.Column('department_id', sa.String(length=36), nullable=True))
    if not _column_exists('incidents_v2', 'assigned_officer_id'):
        op.add_column('incidents_v2', sa.Column('assigned_officer_id', sa.String(length=36), nullable=True))
    try:
        op.create_index('ix_incidents_dept', 'incidents_v2', ['department_id'], unique=False)
        op.create_index('ix_incidents_officer', 'incidents_v2', ['assigned_officer_id'], unique=False)
        op.create_index('ix_incidents_priority', 'incidents_v2', ['priority'], unique=False)
    except Exception:
        pass

    # 3. Table: department_memberships
    if not _table_exists('department_memberships'):
        op.create_table(
            'department_memberships',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('department_id', sa.String(length=36), sa.ForeignKey('departments.id', ondelete='CASCADE'), nullable=False),
            sa.Column('role_in_dept', sa.String(length=30), nullable=False, server_default='officer'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
            sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("role_in_dept IN ('officer','lead','admin')", name='ck_dept_member_role'),
            sa.UniqueConstraint('user_id', 'department_id', name='uq_user_dept'),
        )
        try:
            op.create_index('ix_dept_memberships_user', 'department_memberships', ['user_id'], unique=False)
            op.create_index('ix_dept_memberships_dept', 'department_memberships', ['department_id'], unique=False)
        except Exception:
            pass

    # 4. Table: inspection_records
    if not _table_exists('inspection_records'):
        op.create_table(
            'inspection_records',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('incident_id', sa.String(length=36), sa.ForeignKey('incidents_v2.id', ondelete='CASCADE'), nullable=False),
            sa.Column('officer_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('inspection_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('findings', sa.Text(), nullable=False),
            sa.Column('confirmed_defect_type', sa.String(length=50), nullable=False),
            sa.Column('condition_rating', sa.String(length=20), nullable=False, server_default='moderate'),
            sa.Column('evidence_asset_id', sa.String(length=36), sa.ForeignKey('evidence_assets_v2.id', ondelete='SET NULL'), nullable=True),
            sa.Column('next_action', sa.String(length=50), nullable=False, server_default='schedule_repair'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("condition_rating IN ('minor','moderate','severe','critical')", name='ck_condition_rating'),
        )
        try:
            op.create_index('ix_inspection_incident', 'inspection_records', ['incident_id'], unique=False)
        except Exception:
            pass

    # 5. Table: work_progress_updates
    if not _table_exists('work_progress_updates'):
        op.create_table(
            'work_progress_updates',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('incident_id', sa.String(length=36), sa.ForeignKey('incidents_v2.id', ondelete='CASCADE'), nullable=False),
            sa.Column('officer_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('stage', sa.String(length=50), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('hold_reason', sa.Text(), nullable=True),
            sa.Column('estimated_completion', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        try:
            op.create_index('ix_work_progress_incident', 'work_progress_updates', ['incident_id'], unique=False)
        except Exception:
            pass

    # 6. Table: resolution_records
    if not _table_exists('resolution_records'):
        op.create_table(
            'resolution_records',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('incident_id', sa.String(length=36), sa.ForeignKey('incidents_v2.id', ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column('resolved_by', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('resolution_notes', sa.Text(), nullable=False),
            sa.Column('before_evidence_id', sa.String(length=36), sa.ForeignKey('evidence_assets_v2.id', ondelete='SET NULL'), nullable=True),
            sa.Column('after_evidence_id', sa.String(length=36), sa.ForeignKey('evidence_assets_v2.id', ondelete='SET NULL'), nullable=True),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('approved_by', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        try:
            op.create_index('ix_resolution_incident', 'resolution_records', ['incident_id'], unique=False)
        except Exception:
            pass

    # 7. Table: municipal_internal_notes
    if not _table_exists('municipal_internal_notes'):
        op.create_table(
            'municipal_internal_notes',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('incident_id', sa.String(length=36), sa.ForeignKey('incidents_v2.id', ondelete='CASCADE'), nullable=False),
            sa.Column('author_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('audience', sa.String(length=30), nullable=False, server_default='internal_officers'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("audience IN ('internal_officers','dept_admin_only','municipal_all')", name='ck_note_audience'),
        )
        try:
            op.create_index('ix_internal_notes_incident', 'municipal_internal_notes', ['incident_id'], unique=False)
        except Exception:
            pass

    # 8. Table: citizen_visible_updates
    if not _table_exists('citizen_visible_updates'):
        op.create_table(
            'citizen_visible_updates',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('incident_id', sa.String(length=36), sa.ForeignKey('incidents_v2.id', ondelete='CASCADE'), nullable=False),
            sa.Column('published_by', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('public_message', sa.Text(), nullable=False),
            sa.Column('status_label', sa.String(length=50), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        try:
            op.create_index('ix_citizen_updates_incident', 'citizen_visible_updates', ['incident_id'], unique=False)
        except Exception:
            pass


def downgrade() -> None:
    for tbl in [
        'citizen_visible_updates', 'municipal_internal_notes', 'resolution_records',
        'work_progress_updates', 'inspection_records', 'department_memberships'
    ]:
        if _table_exists(tbl):
            op.drop_table(tbl)

    if _column_exists('incidents_v2', 'assigned_officer_id'):
        op.drop_column('incidents_v2', 'assigned_officer_id')
    if _column_exists('incidents_v2', 'department_id'):
        op.drop_column('incidents_v2', 'department_id')
    if _column_exists('incidents_v2', 'priority'):
        op.drop_column('incidents_v2', 'priority')
    if _column_exists('departments', 'updated_at'):
        op.drop_column('departments', 'updated_at')
    if _column_exists('departments', 'code'):
        op.drop_column('departments', 'code')
