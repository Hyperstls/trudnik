"""Сервис администратора — логирование действий, сбор статистики дашборда.

Вынесен из app/blueprints/admin.py для разделения бизнес-логики и HTTP-слоя.
"""

import json
import logging
from typing import Any, Dict

from app.utils import postgrest_admin_request
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


def log_admin_action(
    action: str,
    table_name: str = None,
    record_id: str = None,
    old_data: Any = None,
    new_data: Any = None,
    user_id: str = None,
    ip_address: str = None,
) -> None:
    """Логирует админское действие в audit_log через PostgREST (C19).

    Args:
        action: название действия ('delete_user', 'verify_employer', и т.д.)
        table_name: имя таблицы, над которой произведено действие
        record_id: ID записи
        old_data: данные до изменения
        new_data: данные после изменения
        user_id: ID администратора (если не передан — из Flask session)
        ip_address: IP администратора (если не передан — из Flask request)
    """
    try:
        # Ленивый импорт Flask-зависимостей (функция может вызываться вне request-контекста)
        if user_id is None:
            from flask import session
            user_id = session.get('user', {}).get('id')
        if ip_address is None:
            from flask import request
            ip_address = request.remote_addr

        payload = {
            'user_id': user_id,
            'action': action,
            'table_name': table_name,
            'record_id': str(record_id) if record_id else None,
            'old_data': json.dumps(old_data) if old_data else None,
            'new_data': json.dumps(new_data) if new_data else None,
            'ip_address': ip_address
        }
        postgrest_admin_request('POST', 'audit_log', data=payload)
    except Exception as e:
        logger.warning("Failed to log admin action: %s", e)


def get_dashboard_stats() -> Dict[str, Any]:
    """Собирает статистику для админ-дашборда через один RPC-вызов + Redis-кеш (60 сек).

    Заменяет 9 отдельных count-запросов одним вызовом get_admin_dashboard_stats().

    Returns:
        Словарь с ключами:
            total_users, workers, employers, admins,
            total_jobs, open_jobs, completed_jobs, cancelled_jobs,
            pending_verifications
    """
    cache_key = 'admin:dashboard:stats'

    # Попытка из Redis-кеша
    try:
        client = get_redis_client()
        if client:
            cached = client.get(cache_key)
            if cached:
                if isinstance(cached, bytes):
                    cached = cached.decode('utf-8')
                return json.loads(cached)
    except Exception as e:
        logger.warning("get_dashboard_stats: Redis cache miss/error: %s", e)

    # RPC-вызов через PostgREST
    from app.utils import postgrest_rpc
    rpc_result = postgrest_rpc('get_admin_dashboard_stats', {}, use_admin=True)

    if not rpc_result.ok:
        logger.error("get_dashboard_stats: RPC failed with status=%s body=%s",
                     rpc_result.status_code, rpc_result.text)
        return {}

    stats = rpc_result.json()
    if not stats:
        return {}

    # Сохранить в Redis на 60 секунд
    try:
        client = get_redis_client()
        if client:
            client.setex(cache_key, 60, json.dumps(stats))
    except Exception as e:
        logger.warning("get_dashboard_stats: Redis cache write error: %s", e)

    return stats
