"""Доступ к чату заявки: проверка, что пользователь — участник.

Участник = принятый работник по заявке (worker_id) ИЛИ владелец задания
(jobs.employer_id через join). Мультирольность: роль не проверяется.
"""

import logging
from typing import Any, Callable, Optional

from app.utils import postgrest_request as _default_request

logger = logging.getLogger(__name__)

RequestFn = Callable[..., Any]

# select по умолчанию покрывает все сценарии (send_message нужен status)
DEFAULT_SELECT = 'worker_id,job_id,status,job:jobs(employer_id)'


def check_participant(application_id: str, user_id: str,
                      select: str = DEFAULT_SELECT,
                      request_fn: Optional[RequestFn] = None
                      ) -> tuple[bool, Optional[dict]]:
    """Проверить участие пользователя в чате заявки.

    Args:
        application_id: ID заявки (чата)
        user_id: ID пользователя
        select: набор колонок для PostgREST (join jobs(employer_id) обязателен)
        request_fn: функция запроса (method, endpoint, **kwargs) -> response;
            если не передана — app.utils.postgrest_request. Пробрасывается
            из blueprints, чтобы mock-патчи postgrest_request в тестах
            продолжали работать.

    Returns:
        (allowed, app_data):
        - (True, dict)   — заявка найдена, пользователь участник;
        - (False, dict)  — заявка найдена, но пользователь не участник;
        - (False, None)  — заявка не найдена или ошибка запроса.
    """
    req = request_fn or _default_request
    try:
        resp = req('GET', f'applications?id=eq.{application_id}&select={select}')
    except Exception as e:
        logger.warning('chat_access.check_participant failed for app %s: %s',
                       application_id, e, exc_info=True)
        return False, None
    if not resp.ok or not resp.json():
        return False, None
    app_data = resp.json()[0]
    employer_id = (app_data.get('job') or {}).get('employer_id')
    if user_id not in (app_data.get('worker_id'), employer_id):
        return False, app_data
    return True, app_data
