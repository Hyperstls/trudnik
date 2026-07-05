"""Сервис управления откликами: отзыв заявок (атомарный RPC)."""

import logging
from typing import Any, Dict

from app.utils import postgrest_rpc

logger = logging.getLogger(__name__)


def withdraw_application_atomic(app_id: str, user_id: str) -> Dict[str, Any]:
    """Отзыв отклика через атомарную RPC. Не fallback на неатомарный путь."""
    rpc_resp = postgrest_rpc('withdraw_application_atomic', {
        'p_application_id': app_id,
        'p_user_id': user_id
    }, use_admin=True)

    if not rpc_resp.ok:
        logger.error('withdraw_application_atomic: RPC failed: %s', rpc_resp.status_code)
        return {'success': False, 'error': 'Сервис временно недоступен'}

    result = rpc_resp.json()
    if isinstance(result, str):
        import json
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            return {'success': False, 'error': 'Неожиданный ответ сервера'}

    if isinstance(result, dict):
        if result.get('success'):
            return {
                'success': True,
                'message': result.get('message', 'Отклик отозван'),
                'new_status': 'withdrawn'
            }
        return {'success': False, 'error': result.get('error', 'Ошибка отзыва')}

    return {'success': False, 'error': 'Неожиданный ответ сервера'}
