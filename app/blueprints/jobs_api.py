"""API-эндпоинты для заданий (JSON-ответы).

Вынесены из jobs.py в рамках рефакторинга Этапа 1.
Содержит: поиск заданий/трудников, справочники, приглашения.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session, current_app, url_for

from app.decorators import login_required, role_required, validate_uuid
from app.services.job_service import (
    check_job_owner,
    is_job_filled,
)
from app.services.notification_service import create as notify
from app.utils import (
    postgrest_request,
    postgrest_admin_request,
    postgrest_rpc,
    sanitize_postgrest,
)

jobs_api_bp = Blueprint('jobs_api', __name__)


# ═══════════════════════════════════════════════════════════════
# Публичные справочники (навыки, вероисповедания)
# ═══════════════════════════════════════════════════════════════

def _dictionary_list(table: str, label: str) -> dict:
    """Универсальный загрузчик публичных справочников (skills/religions).

    Использует service_role (postgrest_admin_request), т.к. справочники нужны
    ДО входа (регистрация) и роль anon/authenticated может не иметь GRANT SELECT
    на этих таблицах. Кэшируем только непустой успешный результат, чтобы
    случайный сбой PostgREST не «застолбил» пустой список на 5 минут.
    """
    import json

    from app.utils.redis_client import get_redis_client

    cache_key = f'dict:{table}'
    try:
        client = get_redis_client()
        if client:
            cached = client.get(cache_key)
            if cached:
                raw = cached.decode('utf-8') if isinstance(cached, bytes) else cached
                return {'success': True, label: json.loads(raw)}
    except Exception:
        pass

    resp = postgrest_admin_request(
        'GET', f'{table}?select=*&order=sort_order.asc,name.asc'
    )
    items = resp.json() if (resp.ok and resp.json()) else []
    if items:
        try:
            client = get_redis_client()
            if client:
                client.setex(cache_key, 300, json.dumps(items, ensure_ascii=False))
        except Exception:
            pass
    return {'success': True, label: items}


@jobs_api_bp.route('/api/skills')
def api_skills():
    """Получить список навыков (JSON)."""
    return _dictionary_list('skills', 'skills')


@jobs_api_bp.route('/api/religions')
def api_religions():
    """Получить список вероисповеданий (JSON)."""
    return _dictionary_list('religions', 'religions')


# ═══════════════════════════════════════════════════════════════
# Приглашения (employer → worker)
# ═══════════════════════════════════════════════════════════════

@jobs_api_bp.route('/api/invite/<job_id>/<worker_id>', methods=['POST'])
@login_required
@role_required('employer')
@validate_uuid('job_id', 'worker_id')
def invite_worker(job_id, worker_id):
    """Работодатель приглашает трудника на задание."""
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Проверить, не приглашён ли уже
    check = postgrest_request(
        'GET',
        f'invitations?job_id=eq.{job_id}&worker_id=eq.{worker_id}&select=id'
    )
    if check.ok and check.json():
        return jsonify({'success': False, 'error': 'Приглашение уже отправлено'}), 409

    # Проверить, есть ли свободные места
    job_resp = postgrest_request(
        'GET',
        f'jobs?id=eq.{job_id}&select=current_workers,max_workers,organization_name'
    )
    if job_resp.ok and job_resp.json():
        job = job_resp.json()[0]
        if job['current_workers'] >= job['max_workers']:
            return jsonify({'success': False, 'error': 'Все места заняты'}), 409

    msg = request.get_json(silent=True) or {}
    inv = postgrest_request('POST', 'invitations', json={
        'job_id': job_id,
        'employer_id': session['user_id'],
        'worker_id': worker_id,
        'message': msg.get('message', '')
    })
    if not inv.ok:
        return jsonify({'success': False, 'error': 'Ошибка при создании приглашения'}), 500

    # Уведомить трудника
    job_name = (
        job_resp.json()[0].get('organization_name', job_id)
        if job_resp.ok and job_resp.json() else job_id
    )
    notify(worker_id, 'application_received', 'Вас пригласили на задание',
           f'Работодатель приглашает вас на задание «{job_name}»',
           data={'job_id': job_id, 'type': 'invitation',
                 'link': url_for('jobs.job_detail', job_id=job_id, _external=True)})

    return jsonify({'success': True, 'message': 'Приглашение отправлено'})


@jobs_api_bp.route('/api/invitations')
@login_required
def list_invitations():
    """JSON API: список приглашений (использует унифицированный сервис)."""
    from app.services.invitation_service import list_invitations as get_invitations
    invitations = get_invitations()
    return jsonify({'invitations': invitations})


@jobs_api_bp.route('/api/invitations/<invitation_id>/respond', methods=['POST'])
@login_required
@role_required('worker')
@validate_uuid('invitation_id')
def respond_invitation(invitation_id):
    """Трудник принимает или отклоняет приглашение.
    При accept используется атомарная RPC accept_invitation_atomic:
    проверка приглашения + создание заявки accepted + инкремент current_workers
    в одной транзакции PostgreSQL."""
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action not in ('accept', 'reject'):
        return jsonify({'success': False, 'error': 'Укажите действие: accept или reject'}), 400

    if action == 'reject':
        # Отклонение — простая операция, не требует атомарности
        inv_resp = postgrest_request(
            'GET',
            f'invitations?id=eq.{invitation_id}&select=worker_id,status'
        )
        if not inv_resp.ok or not inv_resp.json():
            return jsonify({'success': False, 'error': 'Приглашение не найдено'}), 404
        inv = inv_resp.json()[0]
        if inv['worker_id'] != session['user_id']:
            return jsonify({'success': False, 'error': 'Нет доступа'}), 403
        if inv['status'] != 'pending':
            return jsonify({'success': False, 'error': f'Приглашение уже {inv["status"]}'}), 409

        postgrest_request('PATCH', f'invitations?id=eq.{invitation_id}',
                         json={'status': 'rejected', 'responded_at': datetime.now(timezone.utc).isoformat()})
        return jsonify({'success': True, 'new_status': 'rejected'})

    # action == 'accept': атомарная RPC
    rpc_result = postgrest_rpc('accept_invitation_atomic', {
        'p_invitation_id': invitation_id,
        'p_user_id': session['user_id'],
    }, use_admin=True)

    if not rpc_result.ok:
        if rpc_result.status_code == 404:
            return jsonify({'success': False, 'error': 'RPC accept_invitation_atomic не найдена (миграция 061 не применена)'}), 500
        return jsonify({'success': False, 'error': 'Ошибка выполнения операции'}), 500

    result = rpc_result.json()
    if not result or not result.get('success'):
        error_msg = (result or {}).get('error', 'Не удалось принять приглашение')
        status_code = {
            'invitation_not_found': 404,
            'not_target': 403,
            'invitation_not_pending': 409,
            'job_not_found': 404,
            'job_not_open': 409,
            'no_slots': 409,
        }.get((result or {}).get('code', ''), 400)
        return jsonify({'success': False, 'error': error_msg}), status_code

    job_id = result.get('job_id')
    employer_id = result.get('employer_id')
    worker_id = result.get('worker_id')

    # Уведомить работника о принятии
    notify(worker_id, 'application_accepted', 'Приглашение принято',
           f'Ваша заявка на задание #{job_id} принята.',
           data={'job_id': job_id,
                 'link': url_for('jobs.job_detail', job_id=job_id, _external=True)})

    # Уведомить работодателя
    notify(employer_id, 'application_received', 'Приглашение принято',
           f'Трудник принял ваше приглашение на задание',
           data={'job_id': job_id,
                 'link': url_for('jobs.job_detail', job_id=job_id, _external=True)})

    return jsonify({
        'success': True,
        'new_status': 'accepted',
        'job_status': result.get('job_status'),
        'current_workers': result.get('current_workers')
    })
