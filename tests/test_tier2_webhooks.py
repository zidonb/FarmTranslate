"""
Tier 2: Webhook endpoint tests — LemonSqueezy subscription lifecycle.

Now that dashboard.py is migrated to the models layer, we can test the
actual Flask webhook endpoint with a test client. Tests cover:
  - Signature verification (valid + invalid + missing)
  - Full subscription lifecycle via webhook payloads
  - Payment failed/recovered
  - Missing telegram_id
  - Subscription model lifecycle (created→updated→cancelled→expired→resumed)
"""
import pytest
import json
import hmac
import hashlib
from datetime import datetime, timedelta, timezone


# ====================================================================
# FIXTURES
# ====================================================================

WEBHOOK_SECRET = "test_webhook_secret_123"


@pytest.fixture
def dashboard_client():
    """
    Import the actual dashboard app and return a Flask test client.
    The dashboard.py now imports from models.* which are available.
    """
    # dashboard.py checks DASHBOARD_PASSWORD at import time (module level)
    # — our conftest already sets it via os.environ
    import importlib
    import dashboard as dashboard_mod
    importlib.reload(dashboard_mod)  # ensure fresh app with patched config
    dashboard_mod.app.config["TESTING"] = True
    return dashboard_mod.app.test_client()


def sign_payload(payload_bytes: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()


def make_payload(event_name, telegram_id="1001", subscription_id="sub_123",
                 renews_at="2025-03-01T00:00:00Z", ends_at=None,
                 cancelled=False, portal_url="https://portal.example.com"):
    return {
        "meta": {
            "event_name": event_name,
            "custom_data": {"telegram_id": str(telegram_id)} if telegram_id else {}
        },
        "data": {
            "id": subscription_id,
            "attributes": {
                "customer_id": 99999,
                "status": "active",
                "created_at": "2025-01-15T10:00:00Z",
                "renews_at": renews_at,
                "ends_at": ends_at,
                "cancelled": cancelled,
                "urls": {"customer_portal": portal_url}
            }
        }
    }


def post_webhook(client, payload_dict):
    """POST a signed webhook payload to the endpoint."""
    payload_bytes = json.dumps(payload_dict).encode()
    sig = sign_payload(payload_bytes)
    return client.post(
        "/webhook/lemonsqueezy",
        data=payload_bytes,
        content_type="application/json",
        headers={"X-Signature": sig}
    )


# ====================================================================
# SIGNATURE VERIFICATION
# ====================================================================

class TestWebhookSignature:

    def test_no_signature_rejected(self, dashboard_client):
        resp = dashboard_client.post(
            "/webhook/lemonsqueezy",
            data=b'{"test":true}',
            content_type="application/json"
        )
        assert resp.status_code == 401

    def test_invalid_signature_rejected(self, dashboard_client):
        resp = dashboard_client.post(
            "/webhook/lemonsqueezy",
            data=b'{"test":true}',
            content_type="application/json",
            headers={"X-Signature": "bad_sig"}
        )
        assert resp.status_code == 401

    def test_valid_signature_accepted(self, dashboard_client, make_manager):
        """Valid signature + valid payload → 200."""
        make_manager(1001, code="BRIDGE-10001")
        payload = make_payload("subscription_created", telegram_id="1001")
        resp = post_webhook(dashboard_client, payload)
        assert resp.status_code == 200

    def test_tampered_payload_rejected(self, dashboard_client):
        original = json.dumps({"amount": 9}).encode()
        sig = sign_payload(original)
        tampered = json.dumps({"amount": 0}).encode()
        resp = dashboard_client.post(
            "/webhook/lemonsqueezy",
            data=tampered,
            content_type="application/json",
            headers={"X-Signature": sig}
        )
        assert resp.status_code == 401


# ====================================================================
# WEBHOOK EVENT HANDLING
# ====================================================================

class TestWebhookEvents:

    def test_subscription_created(self, dashboard_client, make_manager):
        """subscription_created → subscription saved as active."""
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        payload = make_payload("subscription_created", telegram_id="1001")
        resp = post_webhook(dashboard_client, payload)
        assert resp.status_code == 200
        sub = sub_model.get_by_manager(1001)
        assert sub is not None
        assert sub["status"] == "active"

    def test_subscription_cancelled(self, dashboard_client, make_manager):
        """subscription_cancelled → status updated to cancelled."""
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="active", external_id="sub_123")
        payload = make_payload("subscription_cancelled", telegram_id="1001",
                               ends_at="2025-04-01T00:00:00Z")
        resp = post_webhook(dashboard_client, payload)
        assert resp.status_code == 200
        assert sub_model.get_by_manager(1001)["status"] == "cancelled"

    def test_subscription_expired(self, dashboard_client, make_manager):
        """subscription_expired → status expired, blocks if over limit."""
        import models.subscription as sub_model
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="active")
        # Use 100 messages (over free limit of 3)
        for _ in range(5):
            usage_model.increment(1001)
        payload = make_payload("subscription_expired", telegram_id="1001")
        resp = post_webhook(dashboard_client, payload)
        assert resp.status_code == 200
        assert sub_model.get_by_manager(1001)["status"] == "expired"
        assert usage_model.is_blocked(1001) is True

    def test_subscription_resumed(self, dashboard_client, make_manager):
        """subscription_resumed → active again, user unblocked."""
        import models.subscription as sub_model
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="cancelled")
        usage_model.block(1001)
        payload = make_payload("subscription_resumed", telegram_id="1001")
        resp = post_webhook(dashboard_client, payload)
        assert resp.status_code == 200
        assert sub_model.get_by_manager(1001)["status"] == "active"
        assert usage_model.is_blocked(1001) is False

    def test_subscription_paused(self, dashboard_client, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="active")
        resp = post_webhook(dashboard_client, make_payload("subscription_paused", "1001"))
        assert resp.status_code == 200
        assert sub_model.get_by_manager(1001)["status"] == "paused"

    def test_subscription_unpaused(self, dashboard_client, make_manager):
        import models.subscription as sub_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="paused")
        resp = post_webhook(dashboard_client, make_payload("subscription_unpaused", "1001"))
        assert resp.status_code == 200
        assert sub_model.get_by_manager(1001)["status"] == "active"

    def test_payment_recovered_unblocks(self, dashboard_client, make_manager):
        import models.subscription as sub_model
        import models.usage as usage_model
        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="paused")
        usage_model.block(1001)
        resp = post_webhook(dashboard_client, make_payload("subscription_payment_recovered", "1001"))
        assert resp.status_code == 200
        assert sub_model.get_by_manager(1001)["status"] == "active"
        assert usage_model.is_blocked(1001) is False

    def test_missing_telegram_id(self, dashboard_client):
        """Payload without telegram_id → 200 with note."""
        payload = make_payload("subscription_created", telegram_id=None)
        resp = post_webhook(dashboard_client, payload)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "no telegram_id" in data.get("note", "")

    def test_unknown_event(self, dashboard_client, make_manager):
        """Unknown event name → 200 (logged but not error)."""
        make_manager(1001, code="BRIDGE-10001")
        payload = make_payload("unknown_event_type", "1001")
        resp = post_webhook(dashboard_client, payload)
        assert resp.status_code == 200


# ====================================================================
# FULL LIFECYCLE (model-level, DB-verified)
# ====================================================================

class TestSubscriptionLifecycle:

    def test_full_lifecycle(self, make_manager):
        """created → updated → cancelled → expired → resumed."""
        import models.subscription as sub_model

        make_manager(1001, code="BRIDGE-10001")

        sub_model.save(1001, external_id="sub_1", status="active")
        assert sub_model.is_active(1001) is True

        future = datetime.now(timezone.utc) + timedelta(days=20)
        sub_model.update_status(1001, "cancelled", ends_at=future)
        assert sub_model.is_active(1001) is True  # still has access

        past = datetime.now(timezone.utc) - timedelta(days=1)
        sub_model.update_status(1001, "expired", ends_at=past)
        assert sub_model.is_active(1001) is False

        sub_model.save(1001, external_id="sub_1", status="active")
        assert sub_model.is_active(1001) is True

    def test_expiry_blocks_over_limit_user(self, make_manager):
        import models.subscription as sub_model
        import models.usage as usage_model

        make_manager(1001, code="BRIDGE-10001")
        sub_model.save(1001, status="active")
        for _ in range(5):
            usage_model.increment(1001)

        sub_model.update_status(1001, "expired")
        assert sub_model.is_active(1001) is False
        assert usage_model.is_blocked(1001) is True
