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
        "schedule": 10.0,
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
}

app.autodiscover_tasks(["core"])
import core.tasks  # noqa: E402,F401 — явная регистрация (worker сразу видит имена)
