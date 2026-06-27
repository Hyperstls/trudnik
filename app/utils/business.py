"""Бизнес-хелперы: операции с заданиями, рейтингами, проверки окон."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any


def copy_job(original_job: dict) -> dict:
    """Создать копию задания для дублирования / перепубликации.

    Args:
        original_job: исходный словарь задания.

    Returns:
        Новый словарь с полями для создания копии (status='open', is_paid=True).
    """
    return {
        'employer_id': original_job['employer_id'],
        'organization_name': original_job.get('organization_name', ''),
        'org_description': original_job.get('org_description', ''),
        'object_description': original_job.get('object_description', ''),
        'work_type': original_job.get('work_type', ''),
        'detailed_description': original_job.get('detailed_description', ''),
        'date_time': original_job.get('date_time', ''),
        'payment_amount': original_job.get('payment_amount', 0),
        'address': original_job.get('address', ''),
        'city': original_job.get('city', ''),
        'lat': original_job.get('lat', 0),
        'lng': original_job.get('lng', 0),
        'status': 'open',
        'is_paid': False,
        'tariff': original_job.get('tariff', 'Базовый'),
        'max_workers': original_job.get('max_workers', 1),
        'current_workers': 0,
    }


def check_withdraw_window(job_date_time: Optional[str]) -> bool:
    """Проверить, можно ли отозвать отклик (не позднее 12 часов до начала задания).

    Args:
        job_date_time: ISO-формат даты/времени задания (строка).

    Returns:
        True если до начала более 12 часов и отзыв разрешён, иначе False.
    """
    if not job_date_time:
        return True
    try:
        job_dt = datetime.fromisoformat(job_date_time.replace('Z', '+00:00'))
        return (job_dt - datetime.now(timezone.utc)).total_seconds() > 12 * 3600
    except (ValueError, TypeError):
        return True
