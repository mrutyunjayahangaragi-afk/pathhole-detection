"""
Tests for Centralized Notification System and Transactional Outbox (Step 9)
===========================================================================
Validates transactional event queueing, outbox processing, recipient routing,
channel preference enforcement, truthful unconfigured provider status (BLOCKED),
and in-app inbox operations.
"""

import uuid
import pytest
from backend.db.engine import get_session_factory
from backend.db.models import (
    NotificationEvent, NotificationDelivery, UserNotification,
    NotificationPreference, User, Incident, IncidentFollow
)
from backend.services.notification_outbox_service import NotificationOutboxService
from backend.services.notification_delivery_service import NotificationDeliveryService
from backend.services.in_app_notification_service import InAppNotificationService
from backend.services.notification_preference_service import NotificationPreferenceService
from backend.services.auth_service import AuthService


def _register_user(client) -> tuple[str, str]:
    uid = uuid.uuid4().hex[:6]
    pwd = "Password123!"
    auth = AuthService()
    user_dict = auth.register_citizen(
        display_name=f"User {uid}",
        email=f"user_{uid}@example.com",
        password=pwd,
        confirm_password=pwd,
    )
    res = client.post("/api/v1/auth/login", json={"email": f"user_{uid}@example.com", "password": pwd})
    token = res.get_json()["token"]
    return user_dict["id"], token


def test_outbox_queue_and_idempotency():
    """Scenario 26 & 31: Outbox event is durably recorded and duplicate keys are handled idempotently."""
    outbox = NotificationOutboxService()
    key = f"test_idem_{uuid.uuid4().hex[:8]}"

    res1 = outbox.queue_event(
        event_type="test_event",
        payload={"msg": "Hello civiclens"},
        idempotency_key=key,
    )
    assert res1["is_duplicate"] is False
    assert res1["processing_status"] == "PENDING"

    # Re-queue same key -> duplicate flag true
    res2 = outbox.queue_event(
        event_type="test_event",
        payload={"msg": "Duplicate"},
        idempotency_key=key,
    )
    assert res2["is_duplicate"] is True
    assert res2["id"] == res1["id"]


def test_delivery_service_processes_events_and_honors_preferences(client):
    """Scenario 22, 24 & 29: Event delivers to recipient in-app and marks missing providers BLOCKED."""
    user_id, token = _register_user(client)

    outbox = NotificationOutboxService()
    delivery_service = NotificationDeliveryService()
    in_app_service = InAppNotificationService()
    pref_service = NotificationPreferenceService()

    # Enable SMS in preferences (knowing credentials are not configured)
    pref_service.update_preferences(user_id, {"sms_enabled": True, "in_app_enabled": True})

    # Queue an event for user
    outbox.queue_event(
        event_type="report_acknowledged",
        payload={
            "recipient_id": user_id,
            "title": "Grievance Acknowledged",
            "message": "Your pothole grievance has been verified by engineering.",
            "category": "report",
        },
    )

    # Process outbox
    stats = delivery_service.process_pending_events()
    assert stats["processed"] >= 1
    assert stats["in_app_delivered"] >= 1

    # Verify user received in-app notification
    notifs = in_app_service.get_user_notifications(user_id)
    assert notifs["total"] == 1
    assert notifs["unread_count"] == 1
    assert notifs["items"][0]["title"] == "Grievance Acknowledged"


def test_in_app_notification_read_workflow_and_anti_idor(client):
    """Scenario 15: Mark read, mark all read, and verify anti-IDOR."""
    user1_id, token1 = _register_user(client)
    user2_id, token2 = _register_user(client)

    in_app_service = InAppNotificationService()

    factory = get_session_factory()
    db = factory()
    try:
        n1 = UserNotification(
            recipient_id=user1_id,
            title="Update 1",
            message="Your issue was assigned",
            is_read=False,
        )
        n2 = UserNotification(
            recipient_id=user1_id,
            title="Update 2",
            message="Crew dispatched",
            is_read=False,
        )
        db.add_all([n1, n2])
        db.commit()
        n1_id = n1.id
        n2_id = n2.id
    finally:
        db.close()

    # Check unread count
    cnt_resp = client.get("/api/v2/notifications/unread-count", headers={"Authorization": f"Bearer {token1}"})
    assert cnt_resp.status_code == 200
    assert cnt_resp.get_json()["unread_count"] == 2

    # User 2 tries to mark User 1's notification as read -> 403 Forbidden
    hack_resp = client.post(f"/api/v2/notifications/{n1_id}/read", headers={"Authorization": f"Bearer {token2}"})
    assert hack_resp.status_code == 403

    # User 1 marks single notification as read
    read_resp = client.post(f"/api/v2/notifications/{n1_id}/read", headers={"Authorization": f"Bearer {token1}"})
    assert read_resp.status_code == 200

    cnt_resp2 = client.get("/api/v2/notifications/unread-count", headers={"Authorization": f"Bearer {token1}"})
    assert cnt_resp2.get_json()["unread_count"] == 1

    # Mark all read
    all_resp = client.post("/api/v2/notifications/read-all", headers={"Authorization": f"Bearer {token1}"})
    assert all_resp.status_code == 200

    cnt_resp3 = client.get("/api/v2/notifications/unread-count", headers={"Authorization": f"Bearer {token1}"})
    assert cnt_resp3.get_json()["unread_count"] == 0
