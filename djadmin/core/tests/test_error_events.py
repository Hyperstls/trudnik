"""R039/R040: внутренний error tracking — middleware и админка (152-ФЗ-safe)."""
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from core.middleware import ErrorEventMiddleware
from core.models import ErrorEvent
from core.tests.test_auth import make_profile

User = get_user_model()


class ErrorEventMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ErrorEventMiddleware(lambda request: None)
        self.user = make_profile("err-mw@example.com")

    def _request(self, path="/jobs/42?email=secret@example.com&token=abc", method="get"):
        request = getattr(self.factory, method)(path)
        request.user = self.user
        return request

    def test_unhandled_exception_is_stored_without_pii(self):
        request = self._request()
        try:
            raise ValueError("boom secret@example.com")
        except ValueError as exc:
            exception = exc

        self.assertIsNone(self.middleware.process_exception(request, exception))

        event = ErrorEvent.objects.get()
        self.assertEqual(event.exception_type, "ValueError")
        self.assertEqual(event.path, "/jobs/42")
        self.assertEqual(event.method, "GET")
        self.assertEqual(event.status_code, 500)
        self.assertEqual(event.user_id, self.user.pk)
        self.assertTrue(event.frames)
        for frame in event.frames:
            self.assertEqual(set(frame), {"file", "line", "func"})
            self.assertFalse(frame["file"].startswith("/"), frame["file"])

        stored = json.dumps(
            {
                "exception_type": event.exception_type,
                "path": event.path,
                "method": event.method,
                "frames": event.frames,
            },
            ensure_ascii=False,
        )
        for leaked in ("secret@example.com", "token=abc", "boom"):
            self.assertNotIn(leaked, stored)

    def test_anonymous_exception_has_no_user(self):
        request = self._request()
        request.user = AnonymousUser()

        self.middleware.process_exception(request, RuntimeError("x"))

        self.assertIsNone(ErrorEvent.objects.get().user_id)

    def test_http_errors_are_not_stored(self):
        for exception in (Http404("нет"), PermissionDenied("нельзя")):
            with self.subTest(exception=type(exception).__name__):
                self.assertIsNone(
                    self.middleware.process_exception(self._request(), exception)
                )
        self.assertFalse(ErrorEvent.objects.exists())

    def test_storage_failure_does_not_break_error_handling(self):
        with patch.object(ErrorEvent, "save", side_effect=RuntimeError("db down")):
            with self.assertLogs("core.middleware", level="ERROR"):
                self.assertIsNone(
                    self.middleware.process_exception(self._request(), RuntimeError("orig"))
                )


class ErrorEventAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("err-admin@example.com", "Aa1!aaaa")  # pragma: allowlist secret
        cls.profile = make_profile("err-profile@example.com")

    def setUp(self):
        self.event = ErrorEvent.objects.create(
            exception_type="ValueError",
            path="/jobs/42",
            method="GET",
            status_code=500,
            user_id=self.profile.pk,
            frames=[{"file": "views.py", "line": 10, "func": "job_detail"}],
        )

    def _url(self, name, *args):
        return reverse("admin:core_errorevent_%s" % name, args=args)

    def test_changelist_ok_and_no_pii(self):
        self.client.force_login(self.admin)

        response = self.client.get(self._url("changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ValueError")
        self.assertContains(response, "/jobs/42")
        for column in ("column-method", "column-status_code", "column-user_id"):
            self.assertContains(response, column)
        self.assertNotContains(response, "err-profile@example.com")
        self.assertNotContains(response, "Иван Тестов")

    def test_filters_and_search(self):
        ErrorEvent.objects.create(
            exception_type="KeyError", path="/api/other", method="POST",
        )
        self.client.force_login(self.admin)
        changelist = self._url("changelist")

        for query in ("?exception_type=ValueError", "?method=GET", "?q=/jobs"):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(changelist + query).status_code, 200)

        response = self.client.get(changelist + "?exception_type=ValueError")
        self.assertContains(response, "/jobs/42")
        self.assertNotContains(response, "/api/other")

        response = self.client.get(changelist + "?method=POST")
        self.assertContains(response, "/api/other")
        self.assertNotContains(response, "/jobs/42")

    def test_admin_index_links_events(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "События ошибок")
        self.assertContains(response, self._url("changelist"))

    def test_add_is_forbidden(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self._url("add")).status_code, 403)

    def test_change_is_readonly_and_escapes_frames(self):
        self.event.frames = [{"file": "views.py", "line": 1, "func": "<script>alert(1)</script>"}]
        self.event.save(update_fields=["frames"])
        self.client.force_login(self.admin)
        url = self._url("change", self.event.pk)

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertNotContains(response, "err-profile@example.com")
        self.assertNotContains(response, "Иван Тестов")
        self.assertNotContains(response, 'name="frames"')
        # Сырой frames исключён: JSON с "line" рендерится только внутри frames_pretty.
        self.assertEqual(response.content.count(b"&quot;line&quot;"), 1)
        self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_purge_old_removes_only_stale_events(self):
        old = ErrorEvent.objects.create(
            exception_type="OldError", path="/old", method="GET",
        )
        ErrorEvent.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=91)
        )
        self.client.force_login(self.admin)

        response = self.client.post(self._url("changelist"), {
            "action": "action_purge_old",
            "_selected_action": [str(self.event.pk), str(old.pk)],
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ErrorEvent.objects.filter(pk=old.pk).exists())
        self.assertTrue(ErrorEvent.objects.filter(pk=self.event.pk).exists())
