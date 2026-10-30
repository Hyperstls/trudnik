"""Web Push: подписки и отправка (мок pywebpush, VAPID-настройки)."""
import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.models import PushSubscription
from core.push import send_web_push
from core.tasks import drain_notification_outbox
from core.tests.test_auth import make_profile
from core.tests.test_tasks import make_outbox

SUB_DATA = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/test-push-1",
    "p256dh": "BIPUSH_MOCK_KEY_P256DH_BASE64URL",
    "auth": "mock_auth_key",
}


class PushSubscriptionAPITests(TestCase):
    def setUp(self):
        self.user = make_profile("push-user@example.com")
        self.client.force_login(self.user)

    def test_vapid_public_key_anon(self):
        with override_settings(VAPID_PUBLIC_KEY="mock_pub_key_123"):
            response = self.client.get("/push/vapid-public-key")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["public_key"], "mock_pub_key_123")

    def test_subscribe_unsubscribe(self):
        response = self.client.post("/push/subscription", data=json.dumps(SUB_DATA),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertTrue(PushSubscription.objects.filter(user=self.user, endpoint=SUB_DATA["endpoint"]).exists())
        # дубль не создаёт
        self.client.post("/push/subscription", data=json.dumps(SUB_DATA), content_type="application/json")
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 1)
        # отписка
        self.client.post("/push/unsubscribe", data=json.dumps({"endpoint": SUB_DATA["endpoint"]}),
                         content_type="application/json")
        self.assertFalse(PushSubscription.objects.filter(user=self.user).exists())

    def test_bad_json_400(self):
        response = self.client.post("/push/subscription", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/push/subscription").status_code, 302)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   VAPID_PRIVATE_KEY="mock_priv", VAPID_PUBLIC_KEY="mock_pub")  # pragma: allowlist secret
class PushInDrainTests(TestCase):
    def setUp(self):
        self.user = make_profile("push-drain@example.com")
        PushSubscription.objects.create(user=self.user, endpoint=SUB_DATA["endpoint"],
                                        p256dh=SUB_DATA["p256dh"], auth=SUB_DATA["auth"])
        make_outbox(self.user, title="Push-тест")

    def test_drain_sends_push(self):
        with patch("pywebpush.WebPusher") as mock_pusher:
            mock_pusher.return_value.send.return_value = None
            summary = drain_notification_outbox()
            self.assertIn("processed=1", summary)
            self.assertTrue(mock_pusher.called)

    def test_drain_removes_gone_subscription(self):
        from pywebpush import WebPushException

        class FakeResp:
            status_code = 410

        exc = WebPushException("Subscription deleted", response=FakeResp())
        with patch("pywebpush.WebPusher") as mock_pusher:
            mock_pusher.return_value.send.side_effect = exc
            drain_notification_outbox()
            self.assertFalse(PushSubscription.objects.filter(user=self.user).exists())

    def test_send_web_push_not_configured(self):
        with override_settings(VAPID_PRIVATE_KEY=""):
            result = send_web_push(SUB_DATA, "title", "body")
            self.assertFalse(result["success"])
            self.assertEqual(result["error"], "vapid_not_configured")
