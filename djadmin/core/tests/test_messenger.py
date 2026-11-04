"""Фаза 2е: мессенджер-верификация (контракт Flask сверен)."""
import json

from django.core.cache import cache
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.models import Profile
from core.tests.test_auth import make_profile


@override_settings(MAX_BOT_TOKEN="")
class MessengerVerifyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_profile("msg-user@example.com")

    def test_start_creates_one_time_token(self):
        with override_settings(MAX_BOT_USERNAME="trudnik_bot"):
            self.client.force_login(self.user)
            response = self.client.get("/messenger/start/max")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "https://max.ru/trudnik_bot?start=")
            # токен из ссылки лежит в кэше и указывает на пользователя
            token = response.context["link"].split("start=")[1]
            self.assertEqual(cache.get("msg_verify:%s" % token), str(self.user.pk))

    def test_start_unknown_platform_404(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/messenger/start/telegram").status_code, 404)

    def test_start_requires_login(self):
        self.assertEqual(self.client.get("/messenger/start/max").status_code, 302)

    @override_settings(MAX_WEBHOOK_SECRET="s3cret")  # pragma: allowlist secret
    def test_webhook_fail_closed(self):
        # без секрета — 401
        response = self.client.post("/messenger/webhook/max", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 401)
        # сервис не настроен — 503
        with override_settings(MAX_WEBHOOK_SECRET=""):
            response = self.client.post("/messenger/webhook/max", data="{}", content_type="application/json")
            self.assertEqual(response.status_code, 503)

    @override_settings(MAX_WEBHOOK_SECRET="s3cret")  # pragma: allowlist secret
    def test_webhook_bot_started_verifies_profile(self):
        cache.set("msg_verify:tok123", str(self.user.pk), 600)
        payload = {"update_type": "bot_started", "chat_id": 7,
                   "user": {"user_id": 4242}, "payload": "tok123"}
        response = self.client.post("/messenger/webhook/max", data=json.dumps(payload),
                                    content_type="application/json",
                                    headers={"X-Max-Bot-Api-Secret": "s3cret"})  # pragma: allowlist secret
        self.assertEqual(response.status_code, 200)
        row = Profile.objects.filter(pk=self.user.pk).values(
            "verification_status", "verification_provider", "messenger_user_id").first()
        self.assertEqual(row["verification_status"], "approved")  # RPC настоящий
        self.assertEqual(row["verification_provider"], "max")
        self.assertEqual(row["messenger_user_id"], "4242")
        # токен одноразовый: удалён из кэша после использования
        self.assertIsNone(cache.get("msg_verify:tok123"))

    @override_settings(MAX_WEBHOOK_SECRET="s3cret")  # pragma: allowlist secret
    def test_webhook_message_created_extract_token(self):
        cache.set("msg_verify:tokXYZ", str(self.user.pk), 600)
        payload = {"update_type": "message_created", "chat_id": 8,
                   "message": {"body": {"text": "/start tokXYZ"},
                               "sender": {"user_id": 99}}}
        response = self.client.post("/messenger/webhook/max", data=json.dumps(payload),
                                    content_type="application/json",
                                    headers={"X-Max-Bot-Api-Secret": "s3cret"})  # pragma: allowlist secret
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Profile.objects.get(pk=self.user.pk).messenger_user_id, "99")

    @override_settings(MAX_WEBHOOK_SECRET="s3cret")  # pragma: allowlist secret
    @patch("core.views_messenger._send_max")
    def test_bot_started_without_payload_sends_instruction(self, send):
        payload = {"update_type": "bot_started", "chat_id": 77, "user": {"user_id": 1}}
        response = self.client.post(
            "/messenger/webhook/max", data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Max-Bot-Api-Secret": "s3cret"},  # pragma: allowlist secret
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(send.called)
        self.assertIn("Подтвердить", send.call_args.args[1])

    @override_settings(
        MAX_BOT_TOKEN="test-bot-token",  # pragma: allowlist secret
        MAX_API_URL="https://max.test",
        WORKER_SITE_URL="https://trudnik.test",
    )
    @patch("core.views_messenger._register_subscription", return_value=(True, ""))
    @patch("core.views_messenger.get_max_subscriptions", return_value=[])
    def test_ensure_webhook_registers_subscription(self, _subs, _register):
        from core.views_messenger import ensure_max_webhook

        result = ensure_max_webhook()
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "registered")
        self.assertEqual(result["url"], "https://trudnik.test/messenger/webhook/max")

    @override_settings(MAX_WEBHOOK_SECRET="s3cret")  # pragma: allowlist secret
    @patch("core.views_messenger._send_max")
    def test_webhook_rejects_oversized_body(self, send):
        payload = '{"update_type":"bot_started","chat_id":1,"payload":"' + "x" * 70000 + '"}'
        response = self.client.post(
            "/messenger/webhook/max", data=payload,
            content_type="application/json",
            headers={"X-Max-Bot-Api-Secret": "s3cret"},  # pragma: allowlist secret
        )
        self.assertEqual(response.status_code, 200)
        send.assert_not_called()

    @override_settings(MAX_WEBHOOK_SECRET="s3cret")  # pragma: allowlist secret
    @patch("core.views_messenger._send_max")
    def test_successful_verification_replies_in_chat(self, send):
        cache.set("msg_verify:tok-reply", str(self.user.pk), 600)
        payload = {"update_type": "bot_started", "chat_id": 55,
                   "user": {"user_id": 4242}, "payload": "tok-reply"}
        self.client.post(
            "/messenger/webhook/max", data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Max-Bot-Api-Secret": "s3cret"},  # pragma: allowlist secret
        )
        self.assertTrue(send.called)
        self.assertIn("подтверждён", send.call_args.args[1])

    @override_settings(MAX_WEBHOOK_SECRET="s3cret")  # pragma: allowlist secret
    def test_webhook_unknown_token_no_effect(self):
        payload = {"update_type": "bot_started", "user": {"user_id": 1}, "payload": "nope"}
        response = self.client.post("/messenger/webhook/max", data=json.dumps(payload),
                                    content_type="application/json",
                                    headers={"X-Max-Bot-Api-Secret": "s3cret"})  # pragma: allowlist secret
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(Profile.objects.get(pk=self.user.pk).verification_status, "approved")

    def test_diagnose_staff_only(self):
        self.assertEqual(self.client.get("/messenger/diagnose").status_code, 302)
        admin = Profile.objects.create_superuser("msg-admin@example.com", "Aa1!aaaa")
        self.client.force_login(admin)
        self.assertEqual(self.client.get("/messenger/diagnose").status_code, 200)
