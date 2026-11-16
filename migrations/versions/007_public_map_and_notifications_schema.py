"""public_map_and_notifications_schema

Revision ID: c39d84e1b027
Revises: f7c20a84e025
Create Date: 2026-11-16 14:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c39d84e1b027'
down_revision: Union[str, None] = 'f7c20a84e025'
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
    # 1. Table: incident_publications
    if not _table_exists('incident_publications'):
        op.create_table(
            'incident_publications',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('incident_id', sa.String(length=36), sa.ForeignKey('incidents_v2.id', ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column('visibility_status', sa.String(length=30), server_default='PENDING_PUBLICATION', nullable=False),
            sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('published_by', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('public_title', sa.String(length=255), nullable=True),
            sa.Column('public_description', sa.Text(), nullable=True),
            sa.Column('public_location_name', sa.String(length=255), nullable=True),
            sa.Column('public_latitude', sa.Float(), nullable=True),
            sa.Column('public_longitude', sa.Float(), nullable=True),
            sa.Column('visibility_reason', sa.Text(), nullable=True),
            sa.Column('approved_evidence_ids', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(
                "visibility_status IN ('PRIVATE','PENDING_PUBLICATION','PUBLIC','HIDDEN','ARCHIVED')",
                name='ck_pub_visibility_status'
            )
        )
        op.create_index('ix_inc_pub_visibility', 'incident_publications', ['visibility_status'])
        op.create_index('ix_inc_pub_coords', 'incident_publications', ['public_latitude', 'public_longitude'])

    # 2. Table: incident_follows
    if not _table_exists('incident_follows'):
        op.create_table(
            'incident_follows',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('citizen_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('incident_id', sa.String(length=36), sa.ForeignKey('incidents_v2.id', ondelete='CASCADE'), nullable=False),
            sa.Column('notification_channels', sa.String(length=100), server_default='in_app,email', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('citizen_id', 'incident_id', name='uq_citizen_incident_follow')
        )
        op.create_index('ix_follows_citizen', 'incident_follows', ['citizen_id'])
        op.create_index('ix_follows_incident', 'incident_follows', ['incident_id'])

    # 3. Table: notification_preferences
    if not _table_exists('notification_preferences'):
        op.create_table(
            'notification_preferences',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
            sa.Column('in_app_enabled', sa.Boolean(), server_default='1', nullable=False),
            sa.Column('email_enabled', sa.Boolean(), server_default='1', nullable=False),
            sa.Column('sms_enabled', sa.Boolean(), server_default='0', nullable=False),
            sa.Column('whatsapp_enabled', sa.Boolean(), server_default='0', nullable=False),
            sa.Column('push_enabled', sa.Boolean(), server_default='0', nullable=False),
            sa.Column('quiet_hours_enabled', sa.Boolean(), server_default='0', nullable=False),
            sa.Column('quiet_hours_start', sa.String(length=5), nullable=True),
            sa.Column('quiet_hours_end', sa.String(length=5), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        )
        op.create_index('ix_notif_pref_user', 'notification_preferences', ['user_id'])

    # 4. Table: notification_events (Transactional Outbox)
    if not _table_exists('notification_events'):
        op.create_table(
            'notification_events',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('event_type', sa.String(length=50), nullable=False),
            sa.Column('event_payload', sa.Text(), nullable=False),
            sa.Column('idempotency_key', sa.String(length=100), unique=True, nullable=False),
            sa.Column('processing_status', sa.String(length=30), server_default='PENDING', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "processing_status IN ('PENDING','PROCESSING','COMPLETED','FAILED')",
                name='ck_notif_event_status'
            )
        )
        op.create_index('ix_notif_events_status', 'notification_events', ['processing_status'])
        op.create_index('ix_notif_events_created', 'notification_events', ['created_at'])

    # 5. Table: notification_deliveries
    if not _table_exists('notification_deliveries'):
        op.create_table(
            'notification_deliveries',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('event_id', sa.String(length=36), sa.ForeignKey('notification_events.id', ondelete='CASCADE'), nullable=False),
            sa.Column('recipient_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('channel', sa.String(length=20), nullable=False),
            sa.Column('provider', sa.String(length=50), server_default='internal', nullable=False),
            sa.Column('provider_reference', sa.String(length=100), nullable=True),
            sa.Column('delivery_status', sa.String(length=30), server_default='CREATED', nullable=False),
            sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
            sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_error_code', sa.String(length=50), nullable=True),
            sa.Column('last_error_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(
                "channel IN ('in_app','email','sms','whatsapp','push')",
                name='ck_delivery_channel'
            ),
            sa.CheckConstraint(
                "delivery_status IN ('CREATED','QUEUED','PROCESSING','PROVIDER_ACCEPTED','DELIVERED','FAILED','BLOCKED','CANCELLED')",
                name='ck_delivery_status'
            )
        )
        op.create_index('ix_notif_deliv_recipient', 'notification_deliveries', ['recipient_id'])
        op.create_index('ix_notif_deliv_status', 'notification_deliveries', ['delivery_status'])
        op.create_index('ix_notif_deliv_event', 'notification_deliveries', ['event_id'])

    # 6. Table: user_notifications
    if not _table_exists('user_notifications'):
        op.create_table(
            'user_notifications',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('recipient_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('event_id', sa.String(length=36), sa.ForeignKey('notification_events.id', ondelete='SET NULL'), nullable=True),
            sa.Column('category', sa.String(length=30), server_default='general', nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('language', sa.String(length=5), server_default='en', nullable=False),
            sa.Column('related_report_id', sa.String(length=36), nullable=True),
            sa.Column('related_incident_id', sa.String(length=36), nullable=True),
            sa.Column('is_read', sa.Boolean(), server_default='0', nullable=False),
            sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        )
        op.create_index('ix_user_notif_recipient', 'user_notifications', ['recipient_id'])
        op.create_index('ix_user_notif_unread', 'user_notifications', ['recipient_id', 'is_read'])
        op.create_index('ix_user_notif_created', 'user_notifications', ['created_at'])

    # 7. Table: web_push_subscriptions
    if not _table_exists('web_push_subscriptions'):
        op.create_table(
            'web_push_subscriptions',
            sa.Column('id', sa.String(length=36), primary_key=True),
            sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('endpoint', sa.Text(), nullable=False),
            sa.Column('p256dh', sa.String(length=255), nullable=False),
            sa.Column('auth', sa.String(length=255), nullable=False),
            sa.Column('user_agent', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint('user_id', 'endpoint', name='uq_user_push_endpoint')
        )
        op.create_index('ix_push_sub_user', 'web_push_subscriptions', ['user_id'])


def downgrade() -> None:
    for tbl in [
        'web_push_subscriptions',
        'user_notifications',
        'notification_deliveries',
        'notification_events',
        'notification_preferences',
        'incident_follows',
        'incident_publications',
    ]:
        if _table_exists(tbl):
            op.drop_table(tbl)
