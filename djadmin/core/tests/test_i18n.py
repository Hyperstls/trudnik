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
