"""Сервисный слой для работы с заданиями (jobs).

Хелперы для blueprints/jobs.py и jobs_api.py:
- Получение задания по ID + резолвинг справочных UUID
- Проверки видимости, прав доступа, владения, заполненности

История: 2026-08-16 удалён мёртвый слой поиска (search_jobs/search_workers/
build_*_query/_apply_geo_filters/apply_skill_filter/apply_distance_filter) и
обёртки create_job/update_job/get_job_for_edit/get_employer_jobs — задания
создаются прямым POST /jobs (jobs.py), RPC create_job/update_job в БД никогда
не существовали (см. docs/DEAD_CODE_AUDIT.md, docs/RPC_REGISTRY.md).
"""

import uuid as _uuid
from typing import Optional

from app.utils import (
    postgrest_request,
    postgrest_admin_request,
)


def _is_uuid(value):
    """Проверяет, является ли значение валидным UUID."""
    try:
        _uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False

# ═══════════════════════════════════════════════════════════════
# Хелперы получения данных
# ═══════════════════════════════════════════════════════════════


def get_job_by_id(job_id: str) -> Optional[dict]:
    """Получить задание по ID (admin-запрос, обход RLS).

    Args:
        job_id: UUID задания.

    Returns:
        dict или None.
    """
    resp = postgrest_admin_request(
        'GET',
        f'jobs?id=eq.{job_id}&select=*'
    )
    if resp.ok and resp.json():
        return resp.json()[0]
    return None


def enrich_job_with_references(job: dict) -> None:
    """Разрезолвить UUID-поля work_type и preferred_religion в читаемые названия.

    Мутирует переданный словарь job, заменяя UUID на name.

    Args:
        job: словарь задания (мутабельный).
    """
    if job.get('work_type') and _is_uuid(job['work_type']):
        skill_resp = postgrest_request(
            'GET', f'skills?id=eq.{job["work_type"]}&select=name'
        )
        if skill_resp.ok and skill_resp.json():
            job['work_type'] = skill_resp.json()[0]['name']

    if job.get('preferred_religion') and _is_uuid(job['preferred_religion']):
        rel_resp = postgrest_request(
            'GET', f'religions?id=eq.{job["preferred_religion"]}&select=name'
        )
        if rel_resp.ok and rel_resp.json():
            job['preferred_religion'] = rel_resp.json()[0]['name']


# ═══════════════════════════════════════════════════════════════
# Построение PostgREST-запросов
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# Поиск с пагинацией
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# Клиентские фильтры (fallback, когда БД-фильтрация невозможна)
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# Бизнес-логика: проверки прав и состояний
# ═══════════════════════════════════════════════════════════════


def check_job_visibility(job: dict, user_id: Optional[str] = None,
                         user_role: Optional[str] = None) -> bool:
    """Проверить, видно ли задание текущему пользователю.

    Правила:
    - Владелец (employer) видит задание в ЛЮБОМ статусе и с любым is_paid.
    - Админ видит все задания.
    - Трудник не видит задания от работодателей, которые его заблокировали.
    - Остальные — только в статусах open, completed.

    Args:
        job: словарь задания.
        user_id: ID текущего пользователя (None для гостя).
        user_role: роль текущего пользователя (None для гостя).

    Returns:
        True если задание видно, иначе False.
    """
    # Владелец
    if user_id and job.get('employer_id') == user_id:
        return True
    # Админ
    if user_role == 'admin':
        return True
    # Трудник: проверяем, не заблокирован ли он работодателем задания
    if user_role == 'worker' and user_id and job.get('employer_id'):
        bl_resp = postgrest_request('GET',
            f'blacklists?user_id=eq.{job["employer_id"]}&blocked_user_id=eq.{user_id}&select=user_id')
        if bl_resp.ok and bl_resp.json():
            return False
    # Остальные: только в статусах open, completed
    if job.get('status') not in ('open', 'completed'):
        return False
    return True


def is_job_filled(job: dict) -> bool:
    """Проверить, заполнено ли задание (все места заняты).

    Args:
        job: словарь задания с ключами current_workers, max_workers.

    Returns:
        True если current_workers >= max_workers.
    """
    return job.get('current_workers', 0) >= job.get('max_workers', 1)


def check_job_owner(job_id: str, user_id: str) -> bool:
    """Проверить, что задание принадлежит пользователю.
 
    Args:
        job_id: UUID задания.
        user_id: UUID пользователя.
 
    Returns:
        True если пользователь — владелец задания, иначе False.
    """
    resp = postgrest_request(
        'GET', f'jobs?id=eq.{job_id}&select=employer_id'
    )
    if resp.ok and resp.json():
        return resp.json()[0].get('employer_id') == user_id
    return False


# ═══════════════════════════════════════════════════════════════
# CRUD-операции (вынесены из blueprints/jobs.py)
# ═══════════════════════════════════════════════════════════════


