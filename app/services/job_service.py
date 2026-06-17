"""Сервисный слой для работы с заданиями (jobs).

Выносит бизнес-логику из blueprints/jobs.py:
- Поиск и фильтрация заданий/трудников
- Проверки видимости, прав доступа, владения
- Построение PostgREST-запросов
- Резолвинг справочных UUID
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.utils import (
    calculate_distance,
    sanitize_postgrest,
    supabase_request,
    supabase_admin_request,
    check_withdraw_window,
)

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
    resp = supabase_admin_request(
        'GET',
        f'jobs?id=eq.{job_id}&select=*,photos:job_photos(*)'
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
    if job.get('work_type') and '-' in str(job['work_type']):
        skill_resp = supabase_request(
            'GET', f'skills?id=eq.{job["work_type"]}&select=name'
        )
        if skill_resp.ok and skill_resp.json():
            job['work_type'] = skill_resp.json()[0]['name']

    if job.get('preferred_religion') and '-' in str(job['preferred_religion']):
        rel_resp = supabase_request(
            'GET', f'religions?id=eq.{job["preferred_religion"]}&select=name'
        )
        if rel_resp.ok and rel_resp.json():
            job['preferred_religion'] = rel_resp.json()[0]['name']


# ═══════════════════════════════════════════════════════════════
# Построение PostgREST-запросов
# ═══════════════════════════════════════════════════════════════


def build_job_query(filters: Dict[str, Any]) -> str:
    """Построить PostgREST-строку запроса для поиска заданий.

    Args:
        filters: dict с ключами:
            q, status, min_pay, max_pay, date_from, date_to,
            available_slots, page, per_page, sort, select.

    Returns:
        Строка запроса вида 'select=...&status=eq.open&...'
    """
    select = filters.get('select', '*,photos:job_photos(*)')
    query_parts = [f'select={select}']

    status = filters.get('status')
    if status:
        query_parts.append(f'status=eq.{sanitize_postgrest(status)}')

    q = filters.get('q')
    if q:
        query_parts.append(f'search_vector=fts.russian.{sanitize_postgrest(q)}')

    min_pay = filters.get('min_pay')
    if min_pay is not None:
        query_parts.append(f'payment_amount=gte.{min_pay}')

    max_pay = filters.get('max_pay')
    if max_pay is not None:
        query_parts.append(f'payment_amount=lte.{max_pay}')

    date_from = filters.get('date_from')
    if date_from:
        query_parts.append(f'date_time=gte.{sanitize_postgrest(date_from)}')

    date_to = filters.get('date_to')
    if date_to:
        query_parts.append(f'date_time=lte.{sanitize_postgrest(date_to)}')

    if filters.get('available_slots'):
        query_parts.append('current_workers=lt.max_workers')

    # Пагинация
    page = max(1, filters.get('page', 1))
    per_page = min(100, max(1, filters.get('per_page', 20)))
    offset = (page - 1) * per_page
    query_parts.append(f'limit={per_page}')
    query_parts.append(f'offset={offset}')

    # Сортировка
    sort = filters.get('sort', '')
    if sort == 'date_desc':
        query_parts.append('order=date_time.desc')
    elif sort == 'payment_asc':
        query_parts.append('order=payment_amount.asc')
    elif sort == 'payment_desc':
        query_parts.append('order=payment_amount.desc')
    else:
        query_parts.append('order=created_at.desc')

    return '&'.join(query_parts)


def build_worker_query(filters: Dict[str, Any]) -> str:
    """Построить PostgREST-строку запроса для поиска трудников.

    Args:
        filters: dict с ключами:
            q, skills, rating_min, page, per_page, sort.

    Returns:
        Строка запроса вида 'select=*&role=eq.worker&...'
    """
    query_parts = ['select=*', 'role=eq.worker']

    q = filters.get('q')
    if q:
        query_parts.append(f'search_vector=fts.russian.{sanitize_postgrest(q)}')

    rating_min = filters.get('rating_min')
    if rating_min is not None:
        query_parts.append(f'rating=gte.{rating_min}')

    skills = filters.get('skills', '')
    if skills:
        for sk in skills.split(','):
            sk = sk.strip()
            if sk:
                query_parts.append(f'skills=cs.{{{sanitize_postgrest(sk)}}}')

    page = max(1, filters.get('page', 1))
    per_page = min(100, max(1, filters.get('per_page', 20)))
    offset = (page - 1) * per_page
    query_parts.append(f'limit={per_page}')
    query_parts.append(f'offset={offset}')

    sort = filters.get('sort', '')
    if sort == 'rating_desc':
        query_parts.append('order=rating.desc')
    elif sort == 'payment_asc':
        query_parts.append('order=desired_payment.asc')
    else:
        query_parts.append('order=rating.desc')

    return '&'.join(query_parts)


# ═══════════════════════════════════════════════════════════════
# Поиск с пагинацией
# ═══════════════════════════════════════════════════════════════


def search_jobs(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Поиск заданий с полнотекстовым поиском, фильтрами и пагинацией на стороне БД.

    Args:
        filters: dict (см. build_job_query).

    Returns:
        dict с ключами results, total, page, per_page, pages.
    """
    query = build_job_query(filters)
    headers = {'Prefer': 'count=exact'}
    resp = supabase_request('GET', f'jobs?{query}', headers=headers)

    jobs_list = resp.json() if resp.ok else []
    total = (
        int(resp.headers.get('Content-Range', '0-0/0').split('/')[-1])
        if resp.ok else 0
    )

    # Гео-фильтрация и расчёт расстояния (клиентская)
    lat = filters.get('lat')
    lng = filters.get('lng')
    radius = filters.get('radius', 20)
    sort = filters.get('sort', '')

    if lat is not None and lng is not None:
        try:
            for job in jobs_list:
                if job.get('lat') and job.get('lng'):
                    job['distance'] = calculate_distance(
                        lat, lng, job['lat'], job['lng']
                    )
            if radius:
                jobs_list = [
                    j for j in jobs_list
                    if j.get('distance', float('inf')) <= radius
                ]
            if sort == 'distance':
                jobs_list.sort(key=lambda x: x.get('distance', float('inf')))
        except (TypeError, ValueError) as e:
            from flask import current_app
            current_app.logger.warning('Geo-filter error: %s', str(e))
            # Возвращаем результаты без гео-фильтрации при некорректных параметрах

    # Фильтрация по навыкам (если не использовался FTS)
    skills = filters.get('skills', '')
    q = filters.get('q', '')
    if skills and not q:
        selected = [s.strip().lower() for s in skills.split(',') if s.strip()]
        if selected:
            jobs_list = apply_skill_filter(jobs_list, selected)

    page = max(1, filters.get('page', 1))
    per_page = min(100, max(1, filters.get('per_page', 20)))

    return {
        'results': jobs_list,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': max(1, (total + per_page - 1) // per_page) if total else 1,
    }


def search_workers(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Поиск трудников с полнотекстовым поиском, фильтрами и пагинацией.

    Args:
        filters: dict (см. build_worker_query).

    Returns:
        dict с ключами results, total, page, per_page, pages.
    """
    query = build_worker_query(filters)
    headers = {'Prefer': 'count=exact'}
    resp = supabase_request('GET', f'profiles?{query}', headers=headers)

    workers_list = resp.json() if resp.ok else []
    total = (
        int(resp.headers.get('Content-Range', '0-0/0').split('/')[-1])
        if resp.ok else 0
    )

    lat = filters.get('lat')
    lng = filters.get('lng')
    radius = filters.get('radius', 20)
    sort = filters.get('sort', '')

    if lat is not None and lng is not None:
        try:
            for w in workers_list:
                if w.get('lat') and w.get('lng'):
                    w['distance'] = calculate_distance(
                        lat, lng, w['lat'], w['lng']
                    )
            if radius:
                workers_list = [
                    w for w in workers_list
                    if w.get('distance', float('inf')) <= radius
                ]
            if sort == 'distance':
                workers_list.sort(key=lambda x: x.get('distance', float('inf')))
        except (TypeError, ValueError) as e:
            from flask import current_app
            current_app.logger.warning('Geo-filter error (workers): %s', str(e))

    page = max(1, filters.get('page', 1))
    per_page = min(100, max(1, filters.get('per_page', 20)))

    return {
        'results': workers_list,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': max(1, (total + per_page - 1) // per_page) if total else 1,
    }


# ═══════════════════════════════════════════════════════════════
# Клиентские фильтры (fallback, когда БД-фильтрация невозможна)
# ═══════════════════════════════════════════════════════════════


def apply_skill_filter(jobs_list: List[dict], selected_skills: List[str]) -> List[dict]:
    """Отфильтровать задания по навыкам (клиентский fallback).

    Ищет навыки в полях work_type, object_description, detailed_description.

    Args:
        jobs_list: список заданий (dict).
        selected_skills: список навыков в нижнем регистре.

    Returns:
        Отфильтрованный список заданий.
    """
    if not selected_skills:
        return jobs_list
    return [
        j for j in jobs_list
        if any(
            sk in (
                (j.get('work_type', '') or '') + ' ' +
                (j.get('object_description', '') or '') + ' ' +
                (j.get('detailed_description', '') or '')
            ).lower()
            for sk in selected_skills
        )
    ]


def apply_distance_filter(jobs_list: List[dict], lat: Optional[float],
                          lng: Optional[float], radius: float) -> List[dict]:
    """Отфильтровать задания по расстоянию от заданной точки.

    Args:
        jobs_list: список заданий (dict) с ключами lat, lng.
        lat, lng: координаты центральной точки.
        radius: радиус в км.

    Returns:
        Отфильтрованный список заданий с добавленным ключом 'distance'.
    """
    if lat is None or lng is None:
        return jobs_list
    for job in jobs_list:
        if job.get('lat') and job.get('lng'):
            job['distance'] = calculate_distance(
                lat, lng, job['lat'], job['lng']
            )
        else:
            job['distance'] = float('inf')
    if radius:
        jobs_list = [
            j for j in jobs_list
            if j.get('distance', float('inf')) <= radius
        ]
    return jobs_list


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
        bl_resp = supabase_request('GET',
            f'blacklists?user_id=eq.{job["employer_id"]}&blocked_user_id=eq.{user_id}&select=user_id')
        if bl_resp.ok and bl_resp.json():
            return False
    # Остальные: только в статусах open, completed
    if job.get('status') not in ('open', 'completed'):
        return False
    return True


def can_edit_job(job: dict, user_id: str) -> bool:
    """Проверить, может ли пользователь редактировать задание.

    Args:
        job: словарь задания.
        user_id: ID текущего пользователя.

    Returns:
        True если пользователь — владелец задания.
    """
    return job.get('employer_id') == user_id


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
    resp = supabase_request(
        'GET', f'jobs?id=eq.{job_id}&select=employer_id'
    )
    if resp.ok and resp.json():
        return resp.json()[0].get('employer_id') == user_id
    return False
