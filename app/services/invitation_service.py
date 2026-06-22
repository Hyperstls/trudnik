"""Сервис приглашений: унифицированный список приглашений."""

from typing import Any, Dict, List

from flask import session
from app.utils import supabase_request


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
        resp = supabase_request('GET',
            f'invitations?worker_id=eq.{user_id}'
            f'&select=*,job:jobs(organization_name,payment_amount)'
            f'&order=created_at.desc')
    else:
        resp = supabase_request('GET',
            f'invitations?employer_id=eq.{user_id}'
            f'&select=*,job:jobs(organization_name),worker:profiles!invitations_worker_id_fkey(full_name)'
            f'&order=created_at.desc')

    return resp.json() if resp.ok else []
