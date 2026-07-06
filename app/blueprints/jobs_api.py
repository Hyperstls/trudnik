"""API-эндпоинты для заданий (JSON-ответы).

Вынесены из jobs.py в рамках рефакторинга Этапа 1.
Содержит: поиск заданий/трудников, справочники, приглашения.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session, current_app, url_for

from app.decorators import login_required, role_required, validate_uuid
from app.services.job_service import (
    search_jobs,
    search_workers,
    check_job_owner,
    is_job_filled,
)
from app.services.notification_service import create as notify
from app.utils import (
    cache_for,
    postgrest_request,
    postgrest_admin_request,
    postgrest_rpc,
    sanitize_postgrest,
)

jobs_api_bp = Blueprint('jobs_api', __name__)


# ═══════════════════════════════════════════════════════════════
# Публичные справочники (навыки, вероисповедания)
# ═══════════════════════════════════════════════════════════════

@jobs_api_bp.route('/api/skills')
@cache_for(seconds=300)
def api_skills():
    """Получить список навыков (JSON)."""
    resp = postgrest_request(
        'GET', 'skills?select=*&order=sort_order.asc,name.asc'
    )
    return {'skills': resp.json() if resp.ok else []}


@jobs_api_bp.route('/api/religions')
@cache_for(seconds=300)
def api_religions():
    """Получить список вероисповеданий (JSON)."""
    resp = postgrest_request(
        'GET', 'religions?select=*&order=sort_order.asc,name.asc'
    )
    return {'religions': resp.json() if resp.ok else []}


# ═══════════════════════════════════════════════════════════════
# API поиска (полнотекстовый + фильтры + пагинация)
# ═══════════════════════════════════════════════════════════════

@jobs_api_bp.route('/api/search/jobs')
def api_search_jobs():
    """Поиск заданий с полнотекстовым поиском, фильтрами и пагинацией."""
    import traceback
    try:
        filters = {
            'q': request.args.get('q', ''),
            'status': request.args.get('status', 'open'),
            'lat': request.args.get('lat', type=float),
            'lng': request.args.get('lng', type=float),
            'radius': request.args.get('radius', 20, type=float),
            'min_pay': request.args.get('min_pay', type=int),
            'max_pay': request.args.get('max_pay', type=int),
            'skills': request.args.get('skills', ''),
            'date_from': request.args.get('date_from', ''),
            'date_to': request.args.get('date_to', ''),
            'available_slots': request.args.get('available_slots', 'false').lower() == 'true',
            'page': request.args.get('page', 1, type=int),
            'per_page': request.args.get('per_page', 20, type=int),
            'sort': request.args.get('sort', ''),
        }
        result = search_jobs(filters)
        return result
    except Exception as e:
        current_app.logger.error('api_search_jobs ERROR: %s', e, exc_info=True)
        return jsonify({'error': 'Internal search error'}), 500


@jobs_api_bp.route('/api/search/workers')
def api_search_workers():
    """Поиск трудников с полнотекстовым поиском, фильтрами и пагинацией."""
    filters = {
        'q': request.args.get('q', ''),
        'skills': request.args.get('skills', ''),
        'rating_min': request.args.get('rating_min', type=float),
        'lat': request.args.get('lat', type=float),
        'lng': request.args.get('lng', type=float),
        'radius': request.args.get('radius', 20, type=float),
        'page': request.args.get('page', 1, type=int),
        'per_page': request.args.get('per_page', 20, type=int),
        'sort': request.args.get('sort', ''),
    }
    return search_workers(filters)


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
