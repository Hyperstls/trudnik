"""i18n: переключение языка и английский каталог (J159)."""
from django.test import TestCase
from django.urls import reverse


class LanguageSwitchTests(TestCase):
    def test_default_language_is_russian(self):
        response = self.client.get(reverse("core:login"))
        self.assertContains(response, "Вход в аккаунт")

    def test_switch_to_english(self):
        response = self.client.post(reverse("set_language"), {
            "language": "en", "next": "/login",
        })
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("core:login"))
        self.assertContains(response, "Sign in to your account")
        self.assertContains(response, "Forgot your password?")
        self.assertNotContains(response, "Вход в аккаунт")

    def test_english_form_errors(self):
        self.client.post(reverse("set_language"), {"language": "en", "next": "/register"})
        response = self.client.post(reverse("core:register"), {
            "full_name": "John Smith", "email": "i18n@example.com",
            "password": "short",  # pragma: allowlist secret
            "intent": "both", "consent": "on",
            "website": "", "smart_token": "",
        })
        self.assertContains(response, "Password must contain at least 8 characters.")

    def test_switcher_is_available(self):
        response = self.client.get(reverse("core:login"))
        self.assertContains(response, 'name="language" value="en"')
        self.assertContains(response, 'name="language" value="ru"')

    def test_english_jobs_catalog(self):
        self.client.post(reverse("set_language"), {"language": "en", "next": "/jobs"})
        response = self.client.get(reverse("core:jobs"))
        self.assertContains(response, "Job search")
        self.assertContains(response, ">All</a>")
        self.assertContains(response, "Filters")
        self.assertContains(response, "Sort:")

    def test_english_job_detail(self):
        from core.tests.test_auth import make_profile
        from core.tests.test_flows import make_job

        employer = make_profile("i18n-emp@example.com", role="employer")
        job = make_job(
            employer, work_type="Painting", city="Moscow",
            address="Tverskaya 1", detailed_description="Paint the fence",
            object_description="Country house",
        )
        self.client.post(reverse("set_language"), {"language": "en", "next": "/jobs"})
        response = self.client.get(reverse("core:job_detail", args=[job.pk]))
        self.assertContains(response, "Description")
        self.assertContains(response, "Address")
        self.assertContains(response, "Log in to apply")


class CabinetEnglishTests(TestCase):
    def setUp(self):
        from core.tests.test_auth import make_profile
        from core.tests.test_flows import make_job

        self.worker = make_profile("i18n-cabinet-worker@example.com")
        self.employer = make_profile("i18n-cabinet-emp@example.com", role="employer")
        self.job = make_job(self.employer, work_type="Painting", city="Moscow")

    def _english(self):
        self.client.post(reverse("set_language"), {"language": "en", "next": "/"})

    def test_profile_page_english(self):
        self.client.force_login(self.worker)
        self._english()
        response = self.client.get(reverse("core:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save profile")
        self.assertContains(response, "Data and account")

    def test_my_jobs_english(self):
        self.client.force_login(self.employer)
        self._english()
        response = self.client.get(reverse("core:my_jobs"))
        self.assertContains(response, "My jobs")
        self.assertContains(response, "Trudnik")

    def test_my_applications_english(self):
        self.client.force_login(self.worker)
        self._english()
        response = self.client.get(reverse("core:my_applications"))
        self.assertContains(response, "My applications")

    def test_chats_english(self):
        from core.models import Application

        Application.objects.create(job=self.job, worker=self.worker)
        self.client.force_login(self.worker)
        self._english()
        response = self.client.get(reverse("core:chats"))
        self.assertContains(response, "Chats")

    def test_notifications_english(self):
        self.client.force_login(self.worker)
        self._english()
        response = self.client.get(reverse("core:notifications"))
        self.assertContains(response, "Notifications")

    def test_job_form_english(self):
        self.client.force_login(self.employer)
        self._english()
        response = self.client.get(reverse("core:job_create"))
        self.assertContains(response, "Description")

    def test_status_display_translated(self):
        from django.utils import translation

        with translation.override("en"):
            self.assertEqual(self.job.get_status_display(), "Open")

    def test_english_cabinet_pages_render(self):
        self.client.force_login(self.worker)
        self._english()
        urls = [
            "core:workers", "core:employers", "core:search",
            "core:favorites_page", "core:favorite_jobs", "core:favorite_people",
            "core:blacklist", "core:invitations", "core:notification_prefs",
            "core:my_applications", "core:my_jobs", "core:profile",
            "core:job_create", "core:chats", "core:notifications",
            "core:verify_employer", "core:faq", "core:support", "core:app_download",
        ]
        for name in urls:
            with self.subTest(url=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200, name)

    def test_english_people_pages_render(self):
        from core.models import Application

        Application.objects.create(job=self.job, worker=self.worker)
        self.client.force_login(self.worker)
        self._english()
        for url in (
            reverse("core:worker_detail", args=[self.worker.pk]),
            reverse("core:employer_detail", args=[self.employer.pk]),
            reverse("core:user_ratings", args=[self.worker.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.client.force_login(self.employer)
        self._english()
        response = self.client.get(reverse("core:job_applicants", args=[self.job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Applications")

    def test_english_rating_page(self):
        from core.models import Application

        self.job.status = "completed"
        self.job.save(update_fields=["status"])
        app = Application.objects.create(
            job=self.job, worker=self.worker, status="accepted",
        )
        self.client.force_login(self.employer)
        self._english()
        response = self.client.get(reverse("core:rate_participant", args=[app.pk]))
        self.assertContains(response, "Overall rating")
        self.assertContains(response, "Quality of work")
        self.assertContains(response, "Submit rating")

    def test_js_translation_bridge(self):
        self._english()
        response = self.client.get(reverse("core:login"))
        self.assertContains(response, "TRUDNIK_I18N")
        self.assertContains(response, "Confirm action")
