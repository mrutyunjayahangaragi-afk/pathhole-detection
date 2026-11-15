"""citizen_auth_and_grievance

Revision ID: a3e7b198c214
Revises: 50f57fb42924
Create Date: 2026-11-15 22:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3e7b198c214'
down_revision: Union[str, None] = '50f57fb42924'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users auth columns
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))

    # Citizen reports grievance & location metadata
    op.add_column('citizen_reports_v2', sa.Column('title', sa.String(length=255), nullable=True))
    op.add_column('citizen_reports_v2', sa.Column('reported_severity', sa.String(length=20), server_default='minor', nullable=True))
    op.add_column('citizen_reports_v2', sa.Column('idempotency_key', sa.String(length=64), nullable=True))
    op.add_column('citizen_reports_v2', sa.Column('is_manual_location', sa.Boolean(), server_default='0', nullable=False))
    op.add_column('citizen_reports_v2', sa.Column('latitude', sa.Float(), server_default='0.0', nullable=False))
    op.add_column('citizen_reports_v2', sa.Column('longitude', sa.Float(), server_default='0.0', nullable=False))
    op.add_column('citizen_reports_v2', sa.Column('location_accuracy_m', sa.Float(), nullable=True))
    op.add_column('citizen_reports_v2', sa.Column('address', sa.Text(), nullable=True))

    op.create_index('ix_reports_v2_coords', 'citizen_reports_v2', ['latitude', 'longitude'], unique=False)
    op.create_index('ix_reports_v2_idempotency', 'citizen_reports_v2', ['idempotency_key'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_reports_v2_idempotency', table_name='citizen_reports_v2')
    op.drop_index('ix_reports_v2_coords', table_name='citizen_reports_v2')

    op.drop_column('citizen_reports_v2', 'address')
    op.drop_column('citizen_reports_v2', 'location_accuracy_m')
    op.drop_column('citizen_reports_v2', 'longitude')
    op.drop_column('citizen_reports_v2', 'latitude')
    op.drop_column('citizen_reports_v2', 'is_manual_location')
    op.drop_column('citizen_reports_v2', 'idempotency_key')
    op.drop_column('citizen_reports_v2', 'reported_severity')
    op.drop_column('citizen_reports_v2', 'title')

    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'password_hash')
