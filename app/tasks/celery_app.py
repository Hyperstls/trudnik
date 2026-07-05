"""
Конфигурация Celery для фоновых задач Trudnik.

Брокер: Redis (REDIS_URL, db 0)
Backend: Redis (REDIS_URL, db 1)

Запуск воркера:
    celery -A app.tasks.celery_app worker --loglevel=info
"""

import os
from typing import Any

from celery import Celery

# ═══════════════════════════════════════════════════════════════
# Redis URL из переменной окружения
# ═══════════════════════════════════════════════════════════════

REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Формируем URL для брокера (db 0) и backend (db 1)
# Если в REDIS_URL уже указан номер БД — используем его как есть для брокера,
# а для backend заменяем на db 1
_broker_url: str = REDIS_URL

# Для backend добавляем /1 (или заменяем существующий номер БД)
if "/" in REDIS_URL.rsplit(":", 2)[-1]:
    # В URL уже есть номер БД, например redis://localhost:6379/0
    _backend_url: str = REDIS_URL.rsplit("/", 1)[0] + "/1"
else:
    _backend_url: str = REDIS_URL + "/1"

# ═══════════════════════════════════════════════════════════════
# Экземпляр Celery
# ═══════════════════════════════════════════════════════════════

celery_app: Celery = Celery(
    "trudnik_tasks",
    broker=_broker_url,
    backend=_backend_url,
)

# ═══════════════════════════════════════════════════════════════
# Конфигурация
# ═══════════════════════════════════════════════════════════════

celery_app.conf.update(
    # Сериализация
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Время
    timezone="Europe/Moscow",
    enable_utc=True,
    # Поведение задач
    task_track_started=True,
    task_time_limit=300,          # 5 минут (жёсткое ограничение)
    task_soft_time_limit=240,     # 4 минуты (мягкое ограничение)
    worker_prefetch_multiplier=1, # Не брать больше одной задачи за раз
    task_acks_late=True,          # Подтверждать после выполнения (не теряем задачи при падении)
    task_reject_on_worker_lost=True,  # Переотправлять задачи потерянных worker'ов
    # Повторы по умолчанию
    task_default_retry_delay=60,  # 1 минута между попытками
    task_max_retries=3,
    # Переподключение к брокеру при старте
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    # Graceful shutdown
    worker_shutdown_timeout=60,   # 60 секунд на завершение задач перед SIGKILL
)

# ═══════════════════════════════════════════════════════════════
# Автоматическое обнаружение задач
# ═══════════════════════════════════════════════════════════════

# Позже сюда добавятся email_tasks и push_tasks
celery_app.autodiscover_tasks(["app.tasks"], force=True)

# Расписание Celery Beat для периодических задач
celery_app.conf.beat_schedule = {
    'cleanup-expired-push-subscriptions': {
        'task': 'app.tasks.push_tasks.cleanup_expired_subscriptions',
        'schedule': 3600.0,  # Каждый час (в секундах)
        'options': {
            'expires': 3000,  # Задача истекает через 50 минут
        },
    },
    'cleanup-orphaned-notifications': {
        'task': 'app.tasks.maintenance_tasks.cleanup_orphaned_notifications',
        'schedule': 3600.0,  # Каждый час (в секундах)
        'options': {
            'expires': 3000,  # Задача истекает через 50 минут
        },
    },
    'cleanup-old-email-logs': {
        'task': 'app.tasks.email_tasks.cleanup_old_email_logs',
        'schedule': 86400.0,  # Раз в сутки
        'options': {
            'expires': 43200,  # Задача истекает через 12 часов
        },
    },
    'drain-notification-outbox': {
        'task': 'app.tasks.notification_tasks.drain_notification_outbox',
        'schedule': 10.0,
        'options': {'expires': 8},
    },
    'expire-old-jobs': {
        'task': 'app.tasks.maintenance_tasks.expire_old_jobs',
        'schedule': 3600.0,  # Каждый час
        'options': {
            'expires': 3000,  # Задача истекает через 50 минут
        },
    },
}
