"""Маппинг unmanaged-моделей на реальную схему БД.

Каждое поле каждой модели core обязано указывать на существующую колонку своей
таблицы. Ловит рассинхрону схема↔модели до продакшена.
"""
from django.apps import apps
from django.db import connection
from django.test import TestCase


def table_columns(table: str) -> set[str]:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            [table],
        )
        return {row[0] for row in cur.fetchall()}


class SchemaMappingTests(TestCase):
    def test_every_model_column_exists_in_db(self):
        problems = []
        for model in apps.get_app_config("core").get_models():
            cols = table_columns(model._meta.db_table)
            if not cols:
                problems.append(f"{model.__name__}: таблица {model._meta.db_table} не найдена")
                continue
            for field in model._meta.fields:
                if field.column and field.column not in cols:
                    problems.append(
                        f"{model.__name__}.{field.name} → {model._meta.db_table}.{field.column}: нет колонки"
                    )
        self.assertEqual(problems, [], "\n".join(problems))

    def test_expected_tables_covered(self):
        expected = {
            "profiles", "jobs", "applications", "messages", "notifications",
            "notification_outbox", "ratings", "invitations", "favorites",
            "job_favorites", "blacklists", "user_reports", "employer_details",
            "employer_subscriptions", "job_payments", "_archive_contact_payments",
            "receipts", "job_photos", "skills", "user_skills", "job_skills",
            "religions", "audit_log", "email_log", "push_subscriptions",
            "monetization_settings", "tariff_settings", "site_pages",
        }
        mapped = {m._meta.db_table for m in apps.get_app_config("core").get_models()}
        missing = expected - mapped
        self.assertEqual(missing, set(), f"не замаплены таблицы: {missing}")
