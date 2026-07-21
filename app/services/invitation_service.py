"""Сервис приглашений: унифицированный список приглашений."""

from typing import Any, Dict, List

from flask import session
from app.utils import postgrest_request


def list_invitations(user_id: str = None, role: str = None) -> List[Dict[str, Any]]:
    """Унифицированный список приглашений для работника или работодателя.

    Возвращает приглашения с JOIN-данными (информация о задании и/или работнике).

    Args:
        user_id: UUID пользователя (если None — из сессии).
        role: роль пользователя ('worker' / 'employer', если None — из сессии).

    Returns:
        Список словарей приглашений.
    """
    if user_id is None:
        user_id = session.get('user_id', '')
    if role is None:
        role = session.get('role', 'worker')

    if role == 'worker':
        resp = postgrest_request('GET',
            f'invitations?worker_id=eq.{user_id}'
            f'&select=*,job:jobs(organization_name,payment_amount)'
            f'&order=created_at.desc')
        return resp.json() if resp.ok else []

    # Работодатель: у приглашений нет FK worker_id→profiles, поэтому имена
    # трудников подтягиваем отдельным запросом и приводим к форме item['worker'],
    # которую ожидает вызывающий код.
    resp = postgrest_request('GET',
        f'invitations?employer_id=eq.{user_id}'
        f'&select=*,job:jobs(organization_name)'
        f'&order=created_at.desc')
    items = resp.json() if resp.ok else []
    wids = {it.get('worker_id') for it in items if it.get('worker_id')}
    names = {}
    if wids:
        ids_filter = ','.join(wids)
        wresp = postgrest_request('GET',
            f'profiles?id=in.({ids_filter})&select=id,full_name')
        if wresp.ok and wresp.json():
            names = {p['id']: p.get('full_name') for p in wresp.json()}
    for it in items:
        it['worker'] = {'full_name': names.get(it.get('worker_id'))}
    return items
