"""Сервис избранного: единая логика add/remove/check для всех видов.

Таблицы (схема БД не меняется):
- favorites(user_id, target_id, favorite_type) — kind 'worker' / 'employer'
- job_favorites(user_id, job_id) — kind 'job'

Консолидирует обработку дубликатов PostgREST (400 + body code=23505, B12)
и идемпотентное удаление — раньше этот код был скопирован в
favorites.py / employers.py / jobs.py.
"""
import logging

from app.utils import postgrest_request

logger = logging.getLogger(__name__)

# kind → (таблица, колонка цели, доп. поля для INSERT-полезной нагрузки и фильтров)
_KIND_MAP = {
    'worker': ('favorites', 'target_id', {'favorite_type': 'worker'}),
    'employer': ('favorites', 'target_id', {'favorite_type': 'employer'}),
    'job': ('job_favorites', 'job_id', {}),
}


def _spec(kind: str) -> tuple[str, str, dict]:
    try:
        return _KIND_MAP[kind]
    except KeyError:
        raise ValueError(f'unknown favorite kind: {kind!r}') from None


def _filter_query(user_id: str, kind: str, target_id: str) -> str:
    """PostgREST-фильтр вида 'favorites?user_id=eq.U&target_id=eq.T&favorite_type=eq.worker'."""
    table, column, extra = _spec(kind)
    parts = [f'user_id=eq.{user_id}', f'{column}=eq.{target_id}']
    parts += [f'{k}=eq.{v}' for k, v in extra.items()]
    return f'{table}?' + '&'.join(parts)


def is_duplicate_error(resp) -> bool:
    """True, если ответ PostgREST — unique-violation (уже в избранном).

    B12: PostgREST возвращает 400 + body code=23505 для unique violation (не 409).
    """
    try:
        err_data = resp.json() or {}
    except Exception:
        logger.debug('favorites: non-JSON error body', exc_info=True)
        return False
    return isinstance(err_data, dict) and err_data.get('code') == '23505'


def add_favorite(user_id: str, kind: str, target_id: str):
    """Добавить в избранное.

    Returns:
        (status, resp): status ∈ {'added', 'exists', 'error'} —
        'exists' при дубликате (race condition → ok), 'error' иначе;
        resp — сырой ответ PostgREST (для логирования/status_code у вызывающего).
    """
    table, column, extra = _spec(kind)
    resp = postgrest_request('POST', table,
                             json={'user_id': user_id, column: target_id, **extra})
    if resp.ok:
        return 'added', resp
    if is_duplicate_error(resp):
        return 'exists', resp
    return 'error', resp


def remove_favorite(user_id: str, kind: str, target_id: str):
    """Удалить из избранного (идемпотентно: отсутствие записи — не ошибка).

    Returns:
        Сырой ответ PostgREST (DELETE по фильтру; 204 даже если записи не было).
    """
    return postgrest_request('DELETE', _filter_query(user_id, kind, target_id))


def check_favorite(user_id: str, kind: str, target_id: str) -> bool:
    """Проверить, находится ли target в избранном пользователя."""
    resp = postgrest_request('GET', _filter_query(user_id, kind, target_id))
    return resp.ok and len(resp.json() or []) > 0
