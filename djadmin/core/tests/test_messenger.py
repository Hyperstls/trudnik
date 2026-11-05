"""Мессенджер-верификация MAX: deep link, кнопка подтверждения и webhook."""
import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from core.models import Profile
from core.tests.test_auth import make_profile
from core.views_messenger import (
    NEEDED_UPDATE_TYPES,
    _answer_callback,
    _complete,
    _reply,
    _send_confirm,
    _subscription_signature,
    ensure_max_webhook,
)


@override_settings(MAX_BOT_TOKEN="", MAX_WEBHOOK_SECRET="s3cret")  # pragma: allowlist secret
class MessengerVerifyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_profile("msg-user@example.com")

    def _post(self, payload, secret="s3cret"):  # pragma: allowlist secret
        return self.client.post(
            "/messenger/webhook/max",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"X-Max-Bot-Api-Secret": secret},
        )

    def _callback_payload(self, payload, callback_id="cb-1", uid=4242, chat_id=55):
        return {
            "update_type": "message_callback",
            "callback": {
                "callback_id": callback_id,
                "payload": payload,
                "user": {"user_id": uid},
                "message": {"recipient": {"chat_id": chat_id}},
            },
        }

    # ── start ───────────────────────────────────────────────────────────────

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

    # ── webhook auth/limits ─────────────────────────────────────────────────

    def test_webhook_fail_closed(self):
        # без секрета — 401
        response = self.client.post("/messenger/webhook/max", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 401)
        # сервис не настроен — 503
        with override_settings(MAX_WEBHOOK_SECRET=""):
            response = self.client.post("/messenger/webhook/max", data="{}", content_type="application/json")
            self.assertEqual(response.status_code, 503)

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

    # ── bot_started ─────────────────────────────────────────────────────────

    @patch("core.views_messenger._send_max")
    def test_bot_started_with_token_sends_confirm_button(self, send):
        cache.set("msg_verify:tok123", str(self.user.pk), 600)
        response = self._post({"update_type": "bot_started", "chat_id": 7,
                               "user": {"user_id": 4242}, "payload": "tok123"})
        self.assertEqual(response.status_code, 200)
        send.assert_called_once()
        chat_id, text, attachment = send.call_args.args
        self.assertEqual(chat_id, 7)
        self.assertIn("Подтвердите профиль", text)
        buttons = attachment["payload"]["buttons"]
        self.assertEqual(buttons[0][0]["type"], "callback")
        self.assertEqual(buttons[0][0]["text"], "Подтвердить профиль")
        self.assertEqual(buttons[0][0]["payload"], "confirm:tok123")
        self.assertEqual(buttons[1][0]["type"], "link")
        self.assertTrue(buttons[1][0]["url"].endswith("/profile"))
        # профиль НЕ подтверждён, токен не потрачен
        self.assertNotEqual(Profile.objects.get(pk=self.user.pk).verification_status, "approved")
        self.assertEqual(cache.get("msg_verify:tok123"), str(self.user.pk))

    @patch("core.views_messenger._send_max")
    def test_bot_started_without_payload_sends_instruction(self, send):
        response = self._post({"update_type": "bot_started", "chat_id": 77, "user": {"user_id": 1}})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(send.called)
        self.assertIn("Подтвердить", send.call_args.args[1])
        self.assertIn("Подтвердить профиль", send.call_args.args[1])

    @patch("core.views_messenger._send_max")
    def test_bot_started_with_expired_token_sends_instruction(self, send):
        response = self._post({"update_type": "bot_started", "chat_id": 78,
                               "user": {"user_id": 1}, "payload": "gone"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Подтвердить профиль", send.call_args.args[1])
        self.assertNotEqual(
            send.call_args.args[2]["payload"]["buttons"][0][0].get("type"), "callback",
        )

    def test_webhook_unknown_token_no_effect(self):
        response = self._post({"update_type": "bot_started", "user": {"user_id": 1}, "payload": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(Profile.objects.get(pk=self.user.pk).verification_status, "approved")

    # ── message_created ─────────────────────────────────────────────────────

    @patch("core.views_messenger._send_max")
    def test_message_created_uses_recipient_chat_and_sends_confirm(self, send):
        cache.set("msg_verify:tokM", str(self.user.pk), 600)
        payload = {
            "update_type": "message_created", "chat_id": 999,  # верхний уровень игнорируется
            "message": {"recipient": {"chat_id": 8},
                        "body": {"text": "/start tokM"},
                        "sender": {"user_id": 99}},
        }
        response = self._post(payload)
        self.assertEqual(response.status_code, 200)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], 8)
        self.assertEqual(
            send.call_args.args[2]["payload"]["buttons"][0][0]["payload"], "confirm:tokM",
        )
        self.assertNotEqual(Profile.objects.get(pk=self.user.pk).verification_status, "approved")
        self.assertEqual(cache.get("msg_verify:tokM"), str(self.user.pk))

    @patch("core.views_messenger._send_instruction")
    def test_message_created_without_token_sends_instruction(self, instruction):
        payload = {
            "update_type": "message_created",
            "message": {"recipient": {"chat_id": 8},
                        "body": {"text": "привет"},
                        "sender": {"user_id": 99}},
        }
        response = self._post(payload)
        self.assertEqual(response.status_code, 200)
        instruction.assert_called_once_with(8)

    # ── message_callback ────────────────────────────────────────────────────

    @patch("core.views_messenger._answer_callback")
    def test_message_callback_confirm_verifies_and_answers(self, answer):
        cache.set("msg_verify:tokC", str(self.user.pk), 600)
        response = self._post(self._callback_payload("confirm:tokC"))
        self.assertEqual(response.status_code, 200)
        answer.assert_called_once()
        self.assertEqual(answer.call_args.args[0], "cb-1")
        self.assertIn("подтверждён", answer.call_args.args[1])
        button = answer.call_args.args[2]
        self.assertEqual(button["payload"]["buttons"][0][0]["text"], "Вернуться в профиль")
        row = Profile.objects.filter(pk=self.user.pk).values(
            "verification_status", "verification_provider", "messenger_user_id").first()
        self.assertEqual(row["verification_status"], "approved")  # RPC настоящий
        self.assertEqual(row["verification_provider"], "max")
        self.assertEqual(row["messenger_user_id"], "4242")
        # токен одноразовый: удалён из кэша после использования
        self.assertIsNone(cache.get("msg_verify:tokC"))

    @patch("core.views_messenger.call_rpc")
    @patch("core.views_messenger._answer_callback")
    def test_message_callback_expired_token(self, answer, rpc):
        response = self._post(self._callback_payload("confirm:gone"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ссылка устарела", answer.call_args.args[1])
        rpc.assert_not_called()
        self.assertNotEqual(Profile.objects.get(pk=self.user.pk).verification_status, "approved")

    @patch("core.views_messenger.call_rpc", side_effect=RuntimeError("db down"))
    @patch("core.views_messenger._answer_callback")
    def test_message_callback_rpc_error(self, answer, rpc):
        cache.set("msg_verify:tokE", str(self.user.pk), 600)
        response = self._post(self._callback_payload("confirm:tokE"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось подтвердить", answer.call_args.args[1])
        rpc.assert_called_once()
        self.assertNotEqual(Profile.objects.get(pk=self.user.pk).verification_status, "approved")
        # временный сбой RPC не сжигает ссылку — можно нажать ещё раз
        self.assertEqual(cache.get("msg_verify:tokE"), str(self.user.pk))

    @patch("core.views_messenger.call_rpc")
    @patch("core.views_messenger._answer_callback")
    def test_message_callback_unknown_payload(self, answer, rpc):
        response = self._post(self._callback_payload("open:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Кнопка устарела", answer.call_args.args[1])
        rpc.assert_not_called()

    @patch("core.views_messenger.call_rpc")
    @patch("core.views_messenger._answer_callback")
    def test_complete_returns_ok_and_is_single_use(self, answer, rpc):
        cache.set("msg_verify:tokZ", str(self.user.pk), 600)
        self.assertEqual(_complete("tokZ", "4242", 5, "cb-Z"), "ok")
        self.assertIsNone(cache.get("msg_verify:tokZ"))
        self.assertEqual(_complete("tokZ", "4242", 5, "cb-Z"), "expired")
        self.assertIn("Ссылка устарела", answer.call_args.args[1])
        rpc.assert_called_once_with(
            "verify_via_messenger", str(self.user.pk), "max", "4242",
        )

    @patch("core.views_messenger.call_rpc", side_effect=RuntimeError("db down"))
    @patch("core.views_messenger._answer_callback")
    def test_complete_returns_error_and_restores_token(self, answer, rpc):
        cache.set("msg_verify:tokR", str(self.user.pk), 600)
        self.assertEqual(_complete("tokR", "4242", 5, "cb-R"), "error")
        self.assertIn("Не удалось подтвердить", answer.call_args.args[1])
        self.assertEqual(cache.get("msg_verify:tokR"), str(self.user.pk))
        rpc.assert_called_once()

    # ── diagnose ────────────────────────────────────────────────────────────

    def test_diagnose_staff_only(self):
        self.assertEqual(self.client.get("/messenger/diagnose").status_code, 302)
        admin = Profile.objects.create_superuser("msg-admin@example.com", "Aa1!aaaa")
        self.client.force_login(admin)
        self.assertEqual(self.client.get("/messenger/diagnose").status_code, 200)


@override_settings(MAX_BOT_TOKEN="", MAX_WEBHOOK_SECRET="s3cret")  # pragma: allowlist secret
class MessengerContractTests(TestCase):
    def test_needed_update_types(self):
        self.assertEqual(
            tuple(NEEDED_UPDATE_TYPES),
            ("bot_started", "message_created", "message_callback"),
        )


class ReplyFallbackTests(TestCase):
    @patch("core.views_messenger._send_max")
    @patch("core.views_messenger._answer_callback", return_value=False)
    def test_falls_back_to_chat_when_callback_answer_fails(self, answer, send):
        button = {"type": "inline_keyboard", "payload": {"buttons": []}}
        _reply(55, "cb-1", "Текст", button)
        answer.assert_called_once_with("cb-1", "Текст", button)
        send.assert_called_once_with(55, "Текст", button)

    @patch("core.views_messenger._send_max")
    @patch("core.views_messenger._answer_callback", return_value=True)
    def test_no_duplicate_when_callback_answer_succeeds(self, answer, send):
        _reply(55, "cb-1", "Текст")
        send.assert_not_called()

    @patch("core.views_messenger._send_max")
    @patch("core.views_messenger._answer_callback", return_value=False)
    def test_no_fallback_without_chat_id(self, answer, send):
        _reply(None, "cb-1", "Текст")
        send.assert_not_called()


@override_settings(
    MAX_BOT_TOKEN="test-bot-token",  # pragma: allowlist secret
    MAX_API_URL="https://max.test",
)
class AnswerCallbackTests(TestCase):
    @patch("core.views_messenger.requests.post")
    def test_answer_body_and_query(self, post):
        post.return_value = MagicMock(status_code=200)
        button = {"type": "inline_keyboard", "payload": {"buttons": []}}
        self.assertTrue(_answer_callback("cb-42", "Готово", button))
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://max.test/answers")
        self.assertEqual(kwargs["params"], {"callback_id": "cb-42"})
        self.assertEqual(kwargs["json"], {
            "message": {"text": "Готово", "attachments": [button], "notify": True},
        })

    @patch("core.views_messenger.requests.post")
    def test_answer_without_button_has_empty_attachments(self, post):
        post.return_value = MagicMock(status_code=200)
        self.assertTrue(_answer_callback("cb-1", "Текст"))
        self.assertEqual(post.call_args.kwargs["json"]["message"]["attachments"], [])

    def test_answer_requires_callback_id(self):
        self.assertFalse(_answer_callback("", "Текст"))


@override_settings(
    MAX_BOT_TOKEN="test-bot-token",  # pragma: allowlist secret
    MAX_API_URL="https://max.test",
)
class NoSecretInLogsTests(TestCase):
    @patch("core.views_messenger.requests.post", side_effect=RuntimeError("boom"))
    def test_send_confirm_logs_no_token(self, _post):
        with self.assertLogs("core.views_messenger", level="WARNING") as captured:
            self.assertFalse(_send_confirm(1, "super-secret-token"))
        joined = "\n".join(captured.output)
        self.assertNotIn("super-secret-token", joined)
        self.assertNotIn("confirm:", joined)


@override_settings(
    MAX_BOT_TOKEN="test-bot-token",  # pragma: allowlist secret
    MAX_API_URL="https://max.test",
    WORKER_SITE_URL="https://trudnik.test",
    MAX_WEBHOOK_SECRET="s3cret",  # pragma: allowlist secret
)
class EnsureMaxWebhookTests(TestCase):
    URL = "https://trudnik.test/messenger/webhook/max"
    SIGNATURE = None

    def setUp(self):
        cache.clear()
        self.SIGNATURE = _subscription_signature(self.URL, "s3cret")
        self.addCleanup(cache.clear)

    def _sub(self, url=None, types=None):
        return {"url": url or self.URL,
                "update_types": list(types or NEEDED_UPDATE_TYPES)}

    @patch("core.views_messenger._register_subscription", return_value=(True, ""))
    @patch("core.views_messenger.get_max_subscriptions")
    def test_registers_when_missing_and_remembers_signature(self, subs, register):
        subs.return_value = []
        result = ensure_max_webhook()
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "registered")
        self.assertEqual(result["url"], self.URL)
        register.assert_called_once_with(self.URL)
        self.assertEqual(cache.get("max_webhook:sig"), self.SIGNATURE)

    @patch("core.views_messenger._register_subscription")
    @patch("core.views_messenger.get_max_subscriptions")
    def test_already_registered_when_types_and_signature_match(self, subs, register):
        subs.return_value = [self._sub()]
        cache.set("max_webhook:sig", self.SIGNATURE)
        result = ensure_max_webhook()
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "already_registered")
        register.assert_not_called()

    @patch("core.views_messenger.requests.delete")
    @patch("core.views_messenger._register_subscription", return_value=(True, ""))
    @patch("core.views_messenger.get_max_subscriptions")
    def test_reregisters_when_types_incomplete(self, subs, register, delete):
        subs.return_value = [self._sub(types=("bot_started", "message_created"))]
        cache.set("max_webhook:sig", self.SIGNATURE)  # подпись есть, но типов мало
        delete.return_value = MagicMock(status_code=200)
        result = ensure_max_webhook()
        self.assertEqual(result["action"], "updated")
        delete.assert_called_once()
        self.assertEqual(delete.call_args.kwargs["params"], {"url": self.URL})
        register.assert_called_once_with(self.URL)
        self.assertEqual(cache.get("max_webhook:sig"), self.SIGNATURE)

    @override_settings(MAX_WEBHOOK_SECRET="new-secret")  # pragma: allowlist secret
    @patch("core.views_messenger.requests.delete")
    @patch("core.views_messenger._register_subscription", return_value=(True, ""))
    @patch("core.views_messenger.get_max_subscriptions")
    def test_reregisters_when_secret_changed(self, subs, register, delete):
        subs.return_value = [self._sub()]
        cache.set("max_webhook:sig", self.SIGNATURE)  # подпись от старого секрета
        delete.return_value = MagicMock(status_code=200)
        result = ensure_max_webhook()
        self.assertEqual(result["action"], "updated")
        register.assert_called_once_with(self.URL)
        new_signature = _subscription_signature(self.URL, "new-secret")
        self.assertNotEqual(new_signature, self.SIGNATURE)
        self.assertEqual(cache.get("max_webhook:sig"), new_signature)

    @patch("core.views_messenger.requests.delete")
    @patch("core.views_messenger._register_subscription", return_value=(True, ""))
    @patch("core.views_messenger.get_max_subscriptions")
    def test_deletes_subscriptions_with_old_webhook_urls(self, subs, register, delete):
        old = "https://old.example/messenger/webhook/max"
        subs.return_value = [
            {"url": old, "update_types": list(NEEDED_UPDATE_TYPES)},
            {"url": "https://other.example/hook", "update_types": ["bot_started"]},
        ]
        delete.return_value = MagicMock(status_code=200)
        result = ensure_max_webhook()
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "registered")
        deleted = [call.kwargs["params"]["url"] for call in delete.call_args_list]
        self.assertEqual(deleted, [old])
        register.assert_called_once_with(self.URL)

    @patch("core.views_messenger._register_subscription", return_value=(True, ""))
    @patch("core.views_messenger.get_max_subscriptions")
    def test_reregisters_when_signature_cache_fails(self, subs, register):
        subs.return_value = [self._sub()]
        fake = MagicMock()
        fake.get.side_effect = RuntimeError("cache down")
        with patch("core.views_messenger._cache", return_value=fake):
            result = ensure_max_webhook()
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "updated")
        register.assert_called_once_with(self.URL)

    @override_settings(MAX_BOT_TOKEN="")
    def test_returns_error_without_bot_token(self):
        result = ensure_max_webhook()
        self.assertFalse(result["ok"])
        self.assertIn("MAX_BOT_TOKEN", result["error"])
