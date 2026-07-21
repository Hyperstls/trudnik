"""Короткие хелперы: сессия, построение запросов."""

import re
from typing import Optional

from flask import current_app, flash, session


def _redact_sensitive(text: str) -> str:
    """Маскировать чувствительные данные (email, phone) в тексте для логирования.
    
    Args:
        text: исходный текст, который может содержать PII.
    
    Returns:
        Текст с замаскированными email и телефонами.
    """
    if not text:
        return text
    
    # Маскируем email: user@example.com -> [REDACTED_EMAIL]
    text = re.sub(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        '[REDACTED_EMAIL]',
        text
    )
    
    # Маскируем телефоны (различные форматы): +7..., 8..., (XXX)...
    text = re.sub(
        r'(\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
        '[REDACTED_PHONE]',
        text
    )
    
    return text


def assert_postgrest_ok(resp, operation: str) -> bool:
    """Проверить успешность ответа PostgREST и залогировать/показать ошибку.

    Используется для унификации проверок resp.ok во всех вызовах postgrest_request,
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
    # Маскируем чувствительные данные перед логированием
    redacted_text = _redact_sensitive(text)
    current_app.logger.error(
        'PostgREST request failed: operation=%s status=%s body=%s',
        operation, status, redacted_text,
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
