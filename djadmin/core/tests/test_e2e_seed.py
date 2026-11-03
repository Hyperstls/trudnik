"""E2E seed command contract (J133)."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.models import Job, Profile


class E2ESeedTests(TestCase):
    def test_seed_creates_disposable_users_and_job(self):
        call_command("e2e_seed", stdout=StringIO())

        self.assertTrue(Profile.objects.filter(email="e2e-employer@example.com").exists())
        self.assertTrue(Profile.objects.filter(email="e2e-worker@example.com").exists())
        job = Job.objects.get(work_type="E2E Seed Задача")
        self.assertEqual(job.employer.email, "e2e-employer@example.com")
        self.assertEqual(job.status, Job.Status.OPEN)

        call_command("e2e_seed", "--cleanup", stdout=StringIO())
        self.assertFalse(Profile.objects.filter(email__startswith="e2e-").exists())
        self.assertFalse(Job.objects.filter(work_type="E2E Seed Задача").exists())
