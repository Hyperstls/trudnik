"""Короткие хелперы: сессия, построение запросов."""

from typing import Optional

from flask import current_app, flash, session


def assert_supabase_ok(resp, operation: str) -> bool:
    """Проверить успешность ответа Supabase и залогировать/показать ошибку.

    Используется для унификации проверок resp.ok во всех вызовах supabase_request,
    где проверка отсутствует или неполна (только flash без проверки статуса).

    Args:
        resp: объект ответа requests/httpx (должен иметь .ok, .status_code, .text).
        operation: человекочитаемое описание операции (например, 'смена роли пользователя').

    Returns:
        True если ответ успешный (resp.ok), False если ответ None или статус не 2xx.
    """
    if resp is not None and resp.ok:
        return True
    status = resp.status_code if resp else 'N/A'
    text = (resp.text or '')[:200] if resp else ''
    current_app.logger.error(
        'Supabase request failed: operation=%s status=%s body=%s',
        operation, status, text,
    )
    flash(f'Ошибка сервера при выполнении операции: {operation}', 'danger')
    return False


def uid() -> Optional[str]:
    """Короткий доступ к ID текущего пользователя из сессии.

    Returns:
        user_id или None.
    """
    return session.get('user_id')


def my_query(table: str, field: str = 'user_id', extra: str = '') -> str:
    """Построить PostgREST-запрос для текущего пользователя.

    Args:
        table: имя таблицы.
        field: имя поля для фильтрации по uid.
        extra: дополнительные параметры запроса (например, '&status=eq.open').

    Returns:
        Строка запроса вида 'notifications?user_id=eq.{uid}'.

    Examples:
        my_query('notifications') -> 'notifications?user_id=eq.{uid}'
        my_query('jobs', 'employer_id', '&status=eq.open') -> 'jobs?employer_id=eq.{uid}&status=eq.open'
    """
    u = uid()
    q = f'{table}?{field}=eq.{u}'
    if extra:
        q += extra
    return q
