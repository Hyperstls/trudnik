"""Web Push: подписки и отправка (мок pywebpush, VAPID-настройки)."""
import json
import socket
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

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


@override_settings(WEB_PUSH_ENABLED=True)
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

    def test_subscribe_with_legacy_csrf_header(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.get("/login")
        token = csrf_client.cookies["csrftoken"].value
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            "/push/subscription",
            data=json.dumps(SUB_DATA),
            content_type="application/json",
            HTTP_X_CSRF_TOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            PushSubscription.objects.filter(
                user=self.user, endpoint=SUB_DATA["endpoint"]
            ).exists()
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.notification_prefs.get("push_enabled"))

    def test_bad_json_400(self):
        response = self.client.post("/push/subscription", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/push/subscription").status_code, 302)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   WEB_PUSH_ENABLED=True,
                   VAPID_PRIVATE_KEY="mock_priv", VAPID_PUBLIC_KEY="mock_pub")  # pragma: allowlist secret
class PushInDrainTests(TestCase):
    def setUp(self):
        self._dns = patch(
            "core.push.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                           ("93.184.216.34", 0))],
        )
        self._dns.start()
        self.addCleanup(self._dns.stop)
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


@override_settings(WEB_PUSH_ENABLED=True)
class PushErrorRedactionTests(TestCase):
    """R101: URL/endpoint из исключения pywebpush не попадает в лог."""

    def test_exception_url_is_redacted(self):
        from pywebpush import WebPushException

        exc = WebPushException(
            "boom https://fcm.googleapis.com/fcm/send/secret-endpoint-token"
        )
        with override_settings(
            WEB_PUSH_ENABLED=True,
            VAPID_PRIVATE_KEY="mock_priv",  # pragma: allowlist secret
            VAPID_PUBLIC_KEY="mock_pub",
        ):
            with patch("core.push.socket.getaddrinfo",
                       return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                                      ("93.184.216.34", 0))]):
                with patch("pywebpush.WebPusher") as pusher:
                    pusher.return_value.send.side_effect = exc
                    with self.assertLogs("core.push", level="WARNING") as captured:
                        send_web_push(SUB_DATA, "title", "body")
        joined = chr(10).join(captured.output)
        self.assertNotIn("secret-endpoint-token", joined)
        self.assertIn("<url>", joined)


@override_settings(WEB_PUSH_ENABLED=True)
class PushEndpointValidationTests(TestCase):
    """R055: анти-SSRF фильтр endpoint'а и лимит подписок."""

    def setUp(self):
        self.user = make_profile("push-ssrf@example.com")
        self.client.force_login(self.user)

    def _post(self, endpoint):
        return self.client.post(
            "/push/subscription",
            data=json.dumps({"endpoint": endpoint, **{
                k: v for k, v in SUB_DATA.items() if k != "endpoint"
            }}),
            content_type="application/json",
        )

    def test_rejects_non_https(self):
        self.assertEqual(self._post("http://fcm.googleapis.com/x").status_code, 400)

    def test_rejects_localhost_and_local_names(self):
        for endpoint in (
            "https://localhost/x",
            "https://svc.localhost/x",
            "https://box.local/x",
            "https://node.internal/x",
            "https://router.home.arpa/x",
            "https://intranet/x",  # однословный хост
        ):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self._post(endpoint).status_code, 400)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 0)

    def test_rejects_private_ip_literals(self):
        for endpoint in (
            "https://10.0.0.5/x",
            "https://127.0.0.1/x",
            "https://192.168.1.1/x",
            "https://169.254.1.1/x",
            "https://[fd00::1]/x",
            "https://[::1]/x",
            # legacy-нотации (A2): glibc резолвит их в loopback
            "https://127.1/x",
            "https://0x7f.1/x",
            "https://0177.0.0.1/x",
            "https://2130706433/x",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self._post(endpoint).status_code, 400)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 0)

    def test_accepts_public_ip_literal_and_domain(self):
        self.assertEqual(self._post("https://8.8.8.8/x").status_code, 200)
        # публичный IP в hex-нотации — валиден (8.8.8.8)
        self.assertEqual(self._post("https://0x08080808/x").status_code, 200)
        self.assertEqual(self._post(SUB_DATA["endpoint"]).status_code, 200)

    def test_subscription_limit_drops_oldest(self):
        for i in range(11):
            response = self._post(
                "https://push%d.example-devices.test/endpoint" % i
            )
            self.assertEqual(response.status_code, 200)
        subs = PushSubscription.objects.filter(user=self.user).order_by("pk")
        self.assertEqual(subs.count(), 10)
        self.assertFalse(
            subs.filter(endpoint="https://push0.example-devices.test/endpoint").exists()
        )
        self.assertTrue(
            subs.filter(endpoint="https://push10.example-devices.test/endpoint").exists()
        )


@override_settings(WEB_PUSH_ENABLED=False, VAPID_PRIVATE_KEY="mock_priv",  # pragma: allowlist secret
                   VAPID_PUBLIC_KEY="mock_pub")  # pragma: allowlist secret
class DisabledWebPushTests(TestCase):
    """R088: по умолчанию Web Push выключен — никакой трансграничной передачи."""

    def setUp(self):
        self.user = make_profile("push-off@example.com")
        self.client.force_login(self.user)

    def test_vapid_key_empty_when_disabled(self):
        response = self.client.get("/push/vapid-public-key")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["public_key"], "")

    def test_subscribe_rejected_when_disabled(self):
        response = self.client.post(
            "/push/subscription", data=json.dumps(SUB_DATA),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "push_disabled")
        self.assertFalse(PushSubscription.objects.filter(user=self.user).exists())

    def test_send_reports_disabled_without_pywebpush(self):
        with patch("pywebpush.WebPusher") as mock_pusher:
            result = send_web_push(SUB_DATA, "title", "body")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "push_disabled")
        self.assertFalse(mock_pusher.called)

    def test_drain_does_not_send_push(self):
        PushSubscription.objects.create(
            user=self.user, endpoint=SUB_DATA["endpoint"],
            p256dh=SUB_DATA["p256dh"], auth=SUB_DATA["auth"],
        )
        make_outbox(self.user, title="Push-off")
        with patch("pywebpush.WebPusher") as mock_pusher:
            drain_notification_outbox()
        self.assertFalse(mock_pusher.called)


@override_settings(WEB_PUSH_ENABLED=True,
                   VAPID_PRIVATE_KEY="mock_priv",  # pragma: allowlist secret
                   VAPID_PUBLIC_KEY="mock_pub")
class PushDnsRebindingGuardTests(TestCase):
    """R080: endpoint, резолвящийся внутрь, не получает push."""

    def _send(self, addresses):
        with patch("core.push.socket.getaddrinfo",
                   return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0))
                                 for a in addresses]):
            with patch("pywebpush.WebPusher") as pusher:
                result = send_web_push(SUB_DATA, "title", "body")
        return result, pusher

    def test_private_ip_blocked(self):
        result, pusher = self._send(["10.0.0.5"])
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "endpoint_not_global")
        self.assertFalse(pusher.called)

    def test_loopback_blocked(self):
        result, pusher = self._send(["127.0.0.1"])
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "endpoint_not_global")
        self.assertFalse(pusher.called)

    def test_mixed_public_private_blocked(self):
        result, pusher = self._send(["93.184.216.34", "192.168.1.10"])
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "endpoint_not_global")
        self.assertFalse(pusher.called)

    def test_dns_failure_blocks(self):
        with patch("core.push.socket.getaddrinfo", side_effect=socket.gaierror("no dns")):
            with patch("pywebpush.WebPusher") as pusher:
                result = send_web_push(SUB_DATA, "title", "body")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "endpoint_not_global")
        self.assertFalse(pusher.called)

    def test_public_ip_allowed(self):
        result, pusher = self._send(["93.184.216.34"])
        self.assertTrue(result["success"])
        self.assertTrue(pusher.called)
