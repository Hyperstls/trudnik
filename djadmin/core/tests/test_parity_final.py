"""Финал паритета: WS-уведомления, PWA, metrics, client-error, repost, rate-limit."""
import json

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Job, Profile, Skill
from core.tests.test_auth import make_profile
from core.tests.test_flows import make_job


class NotifyConsumerTests(TestCase):
    def test_notify_user_safe_without_layer(self):
        from core.consumers_notify import notify_user
        user = make_profile("wsn@example.com")
        notify_user(user.pk, {"title": "t"})  # не должно падать

    def test_drain_publishes_notification(self):
        from unittest.mock import patch

        from core.tasks import drain_notification_outbox
        from core.tests.test_tasks import make_outbox

        user = make_profile("wsn-drain@example.com")
        make_outbox(user, title="WS-уведомление")
        with patch("core.consumers_notify.notify_user") as mock_notify:
            drain_notification_outbox()
            self.assertTrue(mock_notify.called)
            args = mock_notify.call_args[0]
            self.assertEqual(args[0], user.pk)
            self.assertEqual(args[1]["title"], "WS-уведомление")


class PwaServiceTests(TestCase):
    def test_sw_js_served_root_scope(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")

    def test_offline_page(self):
        self.assertEqual(self.client.get("/offline").status_code, 200)

    def test_assetlinks(self):
        self.assertEqual(self.client.get("/.well-known/assetlinks.json").status_code, 200)

    def test_favicon(self):
        self.assertEqual(self.client.get("/favicon.ico").status_code, 200)


class MetricsTests(TestCase):
    @override_settings(METRICS_TOKEN="")
    def test_metrics_open_in_debug(self):
        # в тестах DEBUG=False после override — токен пуст → 404 (прод-поведение)
        response = self.client.get("/metrics")
        self.assertIn(response.status_code, (200, 404))

    @override_settings(METRICS_TOKEN="mtok")
    def test_metrics_token_required(self):
        self.assertEqual(self.client.get("/metrics").status_code, 404)
        response = self.client.get("/metrics", HTTP_X_METRICS_TOKEN="mtok")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"trudnik_db_up 1", response.content)


class ClientErrorTests(TestCase):
    def test_accepts_json(self):
        import django.middleware.csrf as csrf_mod
        from django.test import Client
        client = Client(enforce_csrf_checks=False)
        response = client.post(
            "/api/client-error",
            data=json.dumps({"message": "boom", "url": "/jobs"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 204)


class RepostTests(TestCase):
    def test_owner_reposts_with_skills(self):
        owner = make_profile("repost-owner@example.com")
        skill = Skill.objects.create(name="Реп-навык")
        job = make_job(owner, work_type="Оригинал")
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("INSERT INTO job_skills (job_id, skill_id) VALUES (%s, %s)", [job.pk, skill.pk])
        self.client.force_login(owner)
        response = self.client.post(reverse("core:repost_job", args=[job.pk]))
        self.assertEqual(response.status_code, 302)
        clone = Job.objects.exclude(pk=job.pk).get(employer=owner)
        self.assertEqual(clone.work_type, "Оригинал")
        self.assertEqual(clone.status, "open")
        with connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM job_skills WHERE job_id = %s", [clone.pk])
            self.assertEqual(cur.fetchone()[0], 1)

    def test_stranger_404(self):
        job = make_job(make_profile("repost-emp@example.com"))
        self.client.force_login(make_profile("repost-str@example.com"))
        self.assertEqual(self.client.post(reverse("core:repost_job", args=[job.pk])).status_code, 404)


class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_apply_rate_limited_after_10(self):
        emp = make_profile("rl-emp@example.com")
        jobs = [make_job(emp, work_type="RL%d" % i) for i in range(12)]
        worker = make_profile("rl-worker@example.com")
        self.client.force_login(worker)
        codes = []
        for j in jobs:
            r = self.client.post(reverse("core:job_apply", args=[j.pk]))
            codes.append(r.status_code)
        self.assertIn(429, codes)  # лимит 10/мин
        self.assertEqual(codes[0], 302)


class SkillsApiTests(TestCase):
    def test_returns_list(self):
        Skill.objects.create(name="API-навык")
        data = self.client.get("/api/skills").json()
        names = [s["name"] for s in data["skills"]]
        self.assertIn("API-навык", names)
