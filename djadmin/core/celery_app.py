"""Celery-приложение djadmin (паритет Flask-инфраструктуры: Redis-брокер, beat).

Запуск: celery -A core.celery_app worker / beat (см. supervisord.djadmin.conf).
"""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from celery import Celery  # noqa: E402

app = Celery("trudnik_dj", broker=os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL", ""))
app.conf.timezone = "Europe/Moscow"
app.conf.beat_schedule = {
    "drain-notification-outbox": {
        "task": "core.tasks.drain_notification_outbox",
        "schedule": 5.0,
    },
    "expire-old-jobs": {
        "task": "core.tasks.expire_old_jobs",
        "schedule": 3600.0,
    },
    "auto-freeze-on-complaints": {
        "task": "core.tasks.auto_freeze_on_complaints",
        "schedule": 600.0,
    },
    "cleanup-old-email-logs": {
        "task": "core.tasks.cleanup_old_email_logs",
        "schedule": 86400.0,
    },
    "notify-saved-searches": {
        "task": "core.tasks.notify_saved_searches",
        "schedule": 300.0,
    },
    "ensure-max-webhook": {
        "task": "core.tasks.ensure_max_webhook",
        "schedule": 600.0,
    },
    "publish-due-ratings": {
        "task": "core.tasks.publish_due_ratings",
        "schedule": 3600.0,
    },
    "remind-pending-ratings": {
        "task": "core.tasks.remind_pending_ratings",
        "schedule": 21600.0,
    },
    "cleanup-personal-data-retention": {
        "task": "core.tasks.cleanup_personal_data_retention",
        "schedule": 86400.0,
    },
}

app.autodiscover_tasks(["core"])
import core.tasks  # noqa: E402,F401 — явная регистрация (worker сразу видит имена)
