"""Модель Announcement: дефолты, kind choices, ordering, is_active, unmanaged."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.models import Announcement


class AnnouncementModelTests(TestCase):
    def setUp(self):
        Announcement.objects.all().delete()

    def test_create_defaults(self):
        announcement = Announcement.objects.create(title="Приходской субботник")

        self.assertIsNotNone(announcement.id)
        self.assertEqual(announcement.kind, Announcement.Kind.NEWS)
        self.assertEqual(announcement.body, "")
        self.assertEqual(announcement.url, "")
        self.assertEqual(announcement.url_label, "")
        self.assertFalse(announcement.is_pinned)
        self.assertTrue(announcement.is_active)
        self.assertEqual(announcement.sort_order, 0)
        self.assertIsNotNone(announcement.created_at)
        self.assertIsNotNone(announcement.updated_at)

    def test_kind_choices(self):
        self.assertEqual(
            [value for value, _label in Announcement.Kind.choices],
            ["news", "event", "link"],
        )
        for kind in ("news", "event", "link"):
            self.assertEqual(Announcement.objects.create(title=f"kind-{kind}", kind=kind).kind, kind)

    def test_kind_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Announcement.objects.create(title="неверный тип", kind="bogus")

    def test_ordering_pinned_then_sort_order_then_newest(self):
        now = timezone.now()

        old = Announcement.objects.create(title="old", sort_order=2)
        Announcement.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=2))

        new = Announcement.objects.create(title="new", sort_order=1)
        Announcement.objects.filter(pk=new.pk).update(created_at=now)

        same_order_old = Announcement.objects.create(title="same-order-old", sort_order=1)
        Announcement.objects.filter(pk=same_order_old.pk).update(
            created_at=now - timedelta(days=1)
        )

        pinned = Announcement.objects.create(title="pinned-old", is_pinned=True, sort_order=9)
        Announcement.objects.filter(pk=pinned.pk).update(created_at=now - timedelta(days=5))

        self.assertEqual(
            list(Announcement.objects.values_list("title", flat=True)),
            ["pinned-old", "new", "same-order-old", "old"],
        )

    def test_is_active_filter(self):
        Announcement.objects.create(title="active")
        Announcement.objects.create(title="hidden", is_active=False)

        self.assertEqual(
            list(Announcement.objects.filter(is_active=True).values_list("title", flat=True)),
            ["active"],
        )

    def test_unmanaged_meta(self):
        self.assertFalse(Announcement._meta.managed)
        self.assertEqual(Announcement._meta.db_table, "announcements")
        self.assertEqual(
            Announcement._meta.ordering,
            ("-is_pinned", "sort_order", "-created_at"),
        )
