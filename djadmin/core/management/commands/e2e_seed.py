"""Seed/cleanup disposable data for the local Playwright E2E suite (J133)."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Job, Profile

PREFIX = "e2e-"
PASSWORD = "Aa1!aaaa"  # pragma: allowlist secret


class Command(BaseCommand):
    help = "Create or remove e2e-* users and the e2e job for local Playwright runs."

    def add_arguments(self, parser):
        parser.add_argument("--cleanup", action="store_true")

    def handle(self, *args, **options):
        profiles = Profile.objects.filter(email__startswith=PREFIX)
        if options["cleanup"]:
            count = profiles.count()
            profiles.delete()
            self.stdout.write("e2e cleanup: %d profiles removed" % count)
            return

        profiles.delete()
        employer = Profile.objects.create_user(
            PREFIX + "employer@example.com", PASSWORD,
            full_name="E2E Работодатель", role="employer",
            email_verified=True, consented_at=timezone.now(), city="Москва",
        )
        worker = Profile.objects.create_user(
            PREFIX + "worker@example.com", PASSWORD,
            full_name="E2E Трудник", role="worker",
            email_verified=True, consented_at=timezone.now(), city="Москва",
            worker_visibility=True,
        )
        job = Job.objects.create(
            employer=employer,
            work_type="E2E Seed Задача",
            organization_name="E2E Приход",
            detailed_description="Убрать территорию для E2E-проверки.",
            city="Москва",
            address="ул. Тверская, 7",
            lat=55.765252,
            lng=37.609429,
            date_time=timezone.now() + timedelta(days=3),
            payment_amount=1500,
            max_workers=1,
            status=Job.Status.OPEN,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.stdout.write("e2e seed: employer=%s worker=%s job=%s" % (employer.pk, worker.pk, job.pk))
