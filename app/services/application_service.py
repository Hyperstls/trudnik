"""Сервис управления откликами: отзыв заявок (унифицированный)."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from flask import url_for

from app.utils import postgrest_request, postgrest_rpc

logger = logging.getLogger(__name__)


def withdraw_application(app_id: str, user_id: str) -> Dict[str, Any]:
    """Унифицированный отзыв отклика работником (автором).

    Бизнес-правила:
    - pending → withdrawn в любое время (без ограничений)
    - accepted → withdrawn только если > 12 часов до начала задания
    - Если accepted — уменьшает current_workers у задания
    - Уведомляет работодателя через RPC (атомарно, если возможно)

    Args:
        app_id: UUID отклика.
        user_id: UUID пользователя (должен совпадать с worker_id отклика).

    Returns:
        Словарь с ключами success, error/message, new_status.
    """
    # 1. Получить отклик
    app_resp = postgrest_request('GET',
        f'applications?id=eq.{app_id}&select=job_id,worker_id,status')
    if not app_resp.ok or not app_resp.json():
        return {'success': False, 'error': 'Отклик не найден'}

    app_data = app_resp.json()[0]
    if app_data['worker_id'] != user_id:
        return {'success': False, 'error': 'Вы не автор этого отклика'}

    current_status = app_data.get('status', 'pending')
    if current_status == 'withdrawn':
        return {'success': False, 'error': 'Отклик уже отозван'}

    job_id = app_data['job_id']

    # 2. Получить задание
    job_resp = postgrest_request('GET',
        f'jobs?id=eq.{job_id}&select=status,date_time,current_workers,max_workers,employer_id')
    if not job_resp.ok or not job_resp.json():
        return {'success': False, 'error': 'Задание не найдено'}

    job = job_resp.json()[0]

    # 3. Проверка 12-часового окна для accepted
    if current_status == 'accepted':
        date_time_str = job.get('date_time')
        if date_time_str:
            try:
                if isinstance(date_time_str, str):
                    date_time = datetime.fromisoformat(date_time_str.replace('Z', '+00:00'))
                else:
                    date_time = date_time_str
                now = datetime.now(timezone.utc)
                hours_before = (date_time - now).total_seconds() / 3600
                if hours_before < 12:
                    return {
                        'success': False,
                        'error': f'Нельзя отозвать принятый отклик менее чем за 12 часов до начала задания (осталось {hours_before:.1f} ч)'
                    }
            except (ValueError, TypeError):
                pass  # Невалидная дата — пропускаем проверку

    # 4. Если accepted — сначала обновить задание (уменьшить current_workers).
    #    При ошибке PATCH задания — не менять статус заявки, вернуть ошибку.
    #    ВНИМАНИЕ: при сетевом сбое между PATCH задания и PATCH заявки
    #    возможна рассинхронизация. Для атомарности используйте RPC
    #    withdraw_application_atomic (см. withdraw_application_atomic ниже).
    if current_status == 'accepted':
        current_workers = max(0, job.get('current_workers', 1) - 1)
        new_job_status = job.get('status')
        if current_workers == 0 and new_job_status == 'completed':
            new_job_status = 'open'

        job_patch_resp = postgrest_request('PATCH', f'jobs?id=eq.{job_id}', json={
            'current_workers': current_workers,
            'status': new_job_status
        })
        if not job_patch_resp.ok:
            logger.error(
                "withdraw_application: PATCH job failed for job_id=%s status=%s — application NOT changed",
                job_id, job_patch_resp.status_code
            )
            return {
                'success': False,
                'error': 'Не удалось обновить задание, отклик не изменён'
            }

    # 5. Поменять статус отклика на withdrawn
    if current_status == 'accepted':
        patch_resp = postgrest_request('PATCH', f'applications?id=eq.{app_id}', json={'status': 'withdrawn'})
        if not patch_resp.ok:
            logger.error(
                "withdraw_application: PATCH application failed for app_id=%s status=%s — job already updated",
                app_id, patch_resp.status_code
            )
            return {
                'success': True,
                'message': 'Задание обновлено, но не удалось изменить статус отклика',
                'new_status': 'withdrawn'
            }

        # Уведомить работодателя
        from app.services.notification_service import create as notify
        link = url_for('jobs.job_detail', job_id=job_id, _external=True)
        success = notify(
            job['employer_id'], 'withdraw',
            'Работник отозвал отклик',
            f'Принятый работник отозвал отклик с задания #{job_id}',
            data={'job_id': job_id, 'link': link}
        )
        if not success:
            logger.error(
                "withdraw_application: notify() failed for employer_id=%s job_id=%s",
                job['employer_id'], job_id
            )
    elif current_status == 'pending':
        # Для pending — удаляем отклик (старая логика unapply)
        delete_resp = postgrest_request('DELETE', f'applications?id=eq.{app_id}')
        if not delete_resp.ok:
            logger.error(
                "withdraw_application: DELETE application failed for app_id=%s status=%s",
                app_id, delete_resp.status_code
            )

    return {
        'success': True,
        'message': 'Отклик отозван',
        'new_status': 'withdrawn'
    }


def withdraw_application_atomic(app_id: str, user_id: str) -> Dict[str, Any]:
    """Отзыв отклика через атомарную RPC (предпочтительный способ).

    Использует RPC withdraw_application_atomic из миграции 059.
    Если RPC недоступна, фоллбэчится на withdraw_application().

    Args:
        app_id: UUID отклика.
        user_id: UUID пользователя.

    Returns:
        Словарь с ключами success, error/message, new_status.
    """
    # Пробуем атомарный путь
    rpc_resp = postgrest_rpc('withdraw_application_atomic', {
        'p_application_id': app_id,
        'p_user_id': user_id
    })
    if rpc_resp.ok:
        result = rpc_resp.json()
        if isinstance(result, dict) and result.get('success'):
            return {
                'success': True,
                'message': result.get('message', 'Отклик отозван'),
                'new_status': 'withdrawn'
            }
        if isinstance(result, dict) and result.get('error'):
            return {
                'success': False,
                'error': result.get('error', 'Ошибка отзыва')
            }

    # Фоллбэк на ручной отзыв
    logger.warning(
        "withdraw_application_atomic: RPC failed, falling back to manual withdraw for app_id=%s",
        app_id
    )
    return withdraw_application(app_id, user_id)
