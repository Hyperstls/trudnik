"""R006: метаданные сессий и безопасный отзыв без раскрытия session_key."""
import hashlib
import hmac
import time
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.sessions import (
    describe_user_agent,
    iter_user_sessions,
    revoke_user_session,
    session_public_id,
    set_session_meta,
)
from core.tests.test_auth import CACHE_LOCMEM, make_profile

CHROME_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0"


def setUpModule():
    """Сброс per-IP окон тестового клиента (127.0.0.1) перед прогоном.

    Набор core.tests.* ходит с одного IP, а Redis-кэш переживает процесс:
    без сброса повторный прогон упирается в login-лимит 20/час (test_flows)
    или глобальный 120/мин, то есть падает на счётчике, а не на коде.
    """
    window = int(time.time() // 60)
    try:
        cache.delete("rl:ip:login:127.0.0.1")
        for offset in (-1, 0, 1):
            cache.delete("iprl:127.0.0.1:%d" % (window + offset))
    except Exception:
        pass


@override_settings(CACHES=CACHE_LOCMEM)
class SessionPublicIdTests(TestCase):
    def test_public_id_is_hmac_sha256_hex16(self):
        session_key = "0123456789abcdef0123456789abcdef"  # pragma: allowlist secret
        expected = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            session_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:16]

        public_id = session_public_id(session_key)

        self.assertEqual(public_id, expected)
        self.assertEqual(len(public_id), 16)
        self.assertEqual(public_id, session_public_id(session_key))
        self.assertNotEqual(public_id, session_key)


@override_settings(CACHES=CACHE_LOCMEM)
class DescribeUserAgentTests(TestCase):
    def test_browser_and_platform(self):
        cases = [
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 YaBrowser/24.1.0.0 Safari/537.36",
                "Yandex Browser, Windows",
            ),
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
                "Edge, Windows",
            ),
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
                "Opera, Windows",
            ),
            (
                "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
                "Firefox, Linux",
            ),
            (
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                "Chrome, Android",
            ),
            (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 "
                "Mobile/15E148 Safari/604.1",
                "Safari, iOS",
            ),
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Chrome, macOS",
            ),
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
                "Safari, macOS",
            ),
        ]
        for ua, expected in cases:
            with self.subTest(ua=ua):
                self.assertEqual(describe_user_agent(ua), expected)

    def test_unknown_device_is_localized_text(self):
        for ua in ("", None, "curl/8.5.0"):
            with self.subTest(ua=ua):
                self.assertEqual(describe_user_agent(ua), "Неизвестное устройство")


@override_settings(CACHES=CACHE_LOCMEM)
class SetSessionMetaTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_profile("sess-meta@example.com")
        self.factory = RequestFactory()

    def _request(self, user, ua="TestAgent/1.0"):
        request = self.factory.get("/", HTTP_USER_AGENT=ua)
        request.user = user
        request.session = SessionStore()
        request.session.create()
        return request

    def test_authenticated_session_gets_metadata(self):
        request = self._request(self.user)

        set_session_meta(request)

        self.assertEqual(request.session["ua"], "TestAgent/1.0")
        self.assertIn("login_at", request.session)
        self.assertIn("last_seen", request.session)

    def test_anonymous_session_gets_no_metadata(self):
        request = self._request(AnonymousUser())

        set_session_meta(request)

        self.assertNotIn("ua", request.session)
        self.assertNotIn("login_at", request.session)
        self.assertNotIn("last_seen", request.session)

    def test_user_agent_is_truncated_to_300_chars(self):
        request = self._request(self.user, ua="x" * 500)

        set_session_meta(request)

        self.assertEqual(len(request.session["ua"]), 300)

    def test_repeat_call_within_300s_keeps_last_seen(self):
        request = self._request(self.user)
        set_session_meta(request)
        first_seen = request.session["last_seen"]

        with patch("core.sessions.cache.add", return_value=False) as cache_add:
            set_session_meta(request)

        self.assertEqual(request.session["last_seen"], first_seen)
        cache_add.assert_called_with(
            "sess_seen:%s" % request.session.session_key, 1, 300
        )

    def test_cache_failure_does_not_raise(self):
        request = self._request(self.user)

        with patch("core.sessions.cache.add", side_effect=RuntimeError("cache down")):
            set_session_meta(request)

        self.assertIn("login_at", request.session)


@override_settings(CACHES=CACHE_LOCMEM)
class SessionMetaMiddlewareTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_profile("sess-http@example.com")

    def test_middleware_is_after_activity_middleware(self):
        middleware = list(settings.MIDDLEWARE)
        activity = middleware.index("core.middleware.ActivityMiddleware")
        self.assertEqual(
            middleware[activity + 1], "core.middleware.SessionMetaMiddleware"
        )

    def test_authenticated_request_populates_session(self):
        self.client.force_login(self.user)

        response = self.client.get("/jobs", HTTP_USER_AGENT=CHROME_WINDOWS)

        self.assertEqual(response.status_code, 200)
        session = self.client.session
        self.assertEqual(session["ua"], CHROME_WINDOWS)
        self.assertTrue(session.get("login_at"))
        self.assertTrue(session.get("last_seen"))

    def test_anonymous_request_has_no_metadata(self):
        response = self.client.get("/jobs", HTTP_USER_AGENT=CHROME_WINDOWS)

        self.assertEqual(response.status_code, 200)
        session = self.client.session
        self.assertNotIn("ua", session)
        self.assertNotIn("login_at", session)
        self.assertNotIn("last_seen", session)

    def test_repeat_request_within_300s_keeps_last_seen(self):
        self.client.force_login(self.user)
        self.client.get("/jobs", HTTP_USER_AGENT=CHROME_WINDOWS)
        first_seen = self.client.session["last_seen"]

        with patch("core.sessions.cache.add", return_value=False):
            self.client.get("/jobs", HTTP_USER_AGENT=FIREFOX_LINUX)

        session = self.client.session
        self.assertEqual(session["last_seen"], first_seen)
        self.assertEqual(session["ua"], CHROME_WINDOWS)

    def test_middleware_swallows_metadata_exceptions(self):
        self.client.force_login(self.user)

        with patch(
            "core.sessions.set_session_meta", side_effect=RuntimeError("boom")
        ):
            response = self.client.get("/jobs")

        self.assertEqual(response.status_code, 200)

    def test_cache_failure_does_not_break_response(self):
        self.client.force_login(self.user)

        with patch("core.sessions.cache.add", side_effect=RuntimeError("cache down")):
            response = self.client.get("/jobs", HTTP_USER_AGENT=CHROME_WINDOWS)

        self.assertEqual(response.status_code, 200)


@override_settings(CACHES=CACHE_LOCMEM)
class IterUserSessionsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_profile("sess-list@example.com")
        self.other = make_profile("sess-list-other@example.com")
        self.client.force_login(self.user)
        self.client.get("/jobs", HTTP_USER_AGENT=CHROME_WINDOWS)

    def test_only_current_user_sessions_and_no_raw_key(self):
        other_client = Client()
        other_client.force_login(self.other)
        other_client.get("/jobs", HTTP_USER_AGENT=FIREFOX_LINUX)

        sessions = iter_user_sessions(self.user)

        self.assertEqual(len(sessions), 1)
        item = sessions[0]
        self.assertEqual(
            set(item),
            {"public_id", "ua", "description", "login_at", "last_seen", "expire_date"},
        )
        raw_key = self.client.session.session_key
        self.assertNotIn("session_key", item)
        self.assertNotIn(raw_key, item.values())
        self.assertEqual(item["public_id"], session_public_id(raw_key))
        self.assertNotEqual(item["public_id"], raw_key)
        self.assertEqual(item["description"], "Chrome, Windows")

        other_public_id = session_public_id(other_client.session.session_key)
        self.assertNotIn(other_public_id, [s["public_id"] for s in sessions])

    def test_expired_session_is_not_returned(self):
        store = SessionStore()
        Session.objects.create(
            session_key="expired-session-1",
            session_data=store.encode({"_auth_user_id": str(self.user.pk)}),
            expire_date=timezone.now() - timedelta(days=1),
        )

        sessions = iter_user_sessions(self.user)

        self.assertEqual(len(sessions), 1)
        self.assertEqual(
            sessions[0]["public_id"],
            session_public_id(self.client.session.session_key),
        )

    def test_broken_session_data_is_skipped(self):
        Session.objects.create(
            session_key="broken-session-1",
            session_data="!!!not-valid-session-data!!!",
            expire_date=timezone.now() + timedelta(days=1),
        )

        sessions = iter_user_sessions(self.user)

        self.assertEqual(len(sessions), 1)
        self.assertEqual(
            sessions[0]["public_id"],
            session_public_id(self.client.session.session_key),
        )


@override_settings(CACHES=CACHE_LOCMEM)
class RevokeUserSessionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_profile("sess-revoke@example.com")
        self.other = make_profile("sess-revoke-other@example.com")
        self.client.force_login(self.user)

    def test_revoke_own_session_by_public_id(self):
        session_key = self.client.session.session_key
        public_id = session_public_id(session_key)

        result = revoke_user_session(self.user, public_id)

        self.assertEqual(result, public_id)
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())
        self.assertEqual(iter_user_sessions(self.user), [])

    def test_foreign_public_id_returns_none_and_keeps_session(self):
        other_client = Client()
        other_client.force_login(self.other)
        other_key = other_client.session.session_key
        other_public_id = session_public_id(other_key)
        self.assertNotEqual(
            other_public_id, session_public_id(self.client.session.session_key)
        )

        result = revoke_user_session(self.user, other_public_id)

        self.assertIsNone(result)
        self.assertTrue(Session.objects.filter(session_key=other_key).exists())

    def test_unknown_public_id_returns_none(self):
        self.assertIsNone(revoke_user_session(self.user, "0" * 16))
        self.assertIsNone(revoke_user_session(self.user, ""))
        self.assertIsNone(revoke_user_session(self.user, None))


@override_settings(CACHES=CACHE_LOCMEM)
class SessionsPageTests(TestCase):
    """R007: страница /profile/sessions и POST-отзыв сессий."""

    def setUp(self):
        cache.clear()
        self.user = make_profile("sessions-ui@example.com")
        self.other = make_profile("sessions-ui-other@example.com")
        self.client.force_login(self.user)
        self.client.get("/jobs", HTTP_USER_AGENT=CHROME_WINDOWS)
        self.current_key = self.client.session.session_key
        self.current_public_id = session_public_id(self.current_key)

    def _new_session(self, user, ua=FIREFOX_LINUX):
        client = Client()
        client.force_login(user)
        client.get("/jobs", HTTP_USER_AGENT=ua)
        return client

    def test_anonymous_redirected_to_login(self):
        response = Client().get(reverse("core:sessions"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])

    def test_authenticated_sees_current_session(self):
        response = self.client.get(reverse("core:sessions"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Текущая")
        self.assertContains(response, "Chrome, Windows")
        self.assertContains(response, "Вход:")
        self.assertContains(response, "Последняя активность:")
        self.assertNotContains(response, self.current_key)

    def test_current_session_is_first_and_has_display_times(self):
        response = self.client.get(reverse("core:sessions"))

        sessions = response.context["sessions"]
        self.assertTrue(sessions[0]["is_current"])
        self.assertEqual(sessions[0]["public_id"], self.current_public_id)
        self.assertRegex(
            sessions[0]["login_at_display"], r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$"
        )
        self.assertRegex(
            sessions[0]["last_seen_display"], r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$"
        )

    def test_second_session_visible_and_forms_contain_public_ids(self):
        second = self._new_session(self.user)
        second_key = second.session.session_key
        second_public_id = session_public_id(second_key)
        foreign = self._new_session(self.other)
        foreign_public_id = session_public_id(foreign.session.session_key)

        response = self.client.get(reverse("core:sessions"))

        self.assertContains(response, 'name="public_id" value="%s"' % second_public_id)
        self.assertContains(response, 'name="public_id" value="%s"' % self.current_public_id)
        self.assertNotContains(response, foreign_public_id)
        self.assertNotContains(response, second_key)
        self.assertContains(response, "Завершить все другие сессии")

    def test_order_current_first_then_last_seen_desc(self):
        store = SessionStore()
        now = timezone.now()
        for key, hours_ago in (("manual-old", 5), ("manual-new", 1)):
            Session.objects.create(
                session_key=key,
                session_data=store.encode({
                    "_auth_user_id": str(self.user.pk),
                    "ua": FIREFOX_LINUX,
                    "login_at": (now - timedelta(hours=hours_ago)).isoformat(),
                    "last_seen": (now - timedelta(hours=hours_ago)).isoformat(),
                }),
                expire_date=now + timedelta(days=1),
            )

        response = self.client.get(reverse("core:sessions"))

        sessions = response.context["sessions"]
        self.assertEqual(sessions[0]["public_id"], self.current_public_id)
        self.assertEqual(
            [item["public_id"] for item in sessions[1:]],
            [session_public_id("manual-new"), session_public_id("manual-old")],
        )

    def test_missing_metadata_renders_dash(self):
        store = SessionStore()
        Session.objects.create(
            session_key="manual-nometa",
            session_data=store.encode({"_auth_user_id": str(self.user.pk)}),
            expire_date=timezone.now() + timedelta(days=1),
        )

        response = self.client.get(reverse("core:sessions"))

        item = next(
            s for s in response.context["sessions"]
            if s["public_id"] == session_public_id("manual-nometa")
        )
        self.assertEqual(item["login_at_display"], "—")
        self.assertEqual(item["last_seen_display"], "—")

    def test_revoke_other_session_keeps_current(self):
        second = self._new_session(self.user)
        second_key = second.session.session_key

        response = self.client.post(
            reverse("core:session_revoke"),
            {"public_id": session_public_id(second_key)},
        )

        self.assertRedirects(response, "/profile/sessions")
        self.assertFalse(Session.objects.filter(session_key=second_key).exists())
        self.assertTrue(Session.objects.filter(session_key=self.current_key).exists())

    def test_revoke_current_session_logs_out(self):
        response = self.client.post(
            reverse("core:session_revoke"), {"public_id": self.current_public_id}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/login")
        self.assertFalse(Session.objects.filter(session_key=self.current_key).exists())
        follow = self.client.get(reverse("core:sessions"))
        self.assertEqual(follow.status_code, 302)
        self.assertIn("/login", follow["Location"])

    def test_revoke_all_others_reports_count(self):
        self._new_session(self.user)
        self._new_session(self.user)

        response = self.client.post(
            reverse("core:session_revoke"), {"scope": "others"}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Завершено других сессий: 2")
        remaining = iter_user_sessions(self.user)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["public_id"], self.current_public_id)
        self.assertTrue(Session.objects.filter(session_key=self.current_key).exists())

    def test_foreign_public_id_does_not_revoke(self):
        foreign = self._new_session(self.other)
        foreign_key = foreign.session.session_key

        response = self.client.post(
            reverse("core:session_revoke"),
            {"public_id": session_public_id(foreign_key)},
        )

        self.assertRedirects(response, "/profile/sessions")
        self.assertTrue(Session.objects.filter(session_key=foreign_key).exists())

    def test_forms_have_csrf_token(self):
        self._new_session(self.user)

        response = self.client.get(reverse("core:sessions"))

        self.assertContains(response, "csrfmiddlewaretoken")

    def test_revoke_requires_post(self):
        response = self.client.get(reverse("core:session_revoke"))

        self.assertEqual(response.status_code, 405)

    def test_revoke_without_csrf_token_is_rejected(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.post(
            reverse("core:session_revoke"), {"public_id": self.current_public_id}
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Session.objects.filter(session_key=self.current_key).exists())

    def test_revoke_is_rate_limited(self):
        for _ in range(10):
            self.client.post(reverse("core:session_revoke"), {"public_id": "0" * 16})

        response = self.client.post(
            reverse("core:session_revoke"), {"public_id": "0" * 16}, follow=True
        )

        self.assertContains(response, "Слишком часто")
