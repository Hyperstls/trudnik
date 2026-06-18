"""API-эндпоинты для заданий (JSON-ответы).

Вынесены из jobs.py в рамках рефакторинга Этапа 1.
Содержит: поиск заданий/трудников, справочники, приглашения.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session, current_app, url_for

from app.decorators import login_required, role_required
from app.services.job_service import (
    search_jobs,
    search_workers,
    check_job_owner,
    is_job_filled,
)
from app.services.notification_service import create as notify
from app.utils import (
    cache_for,
    supabase_request,
    supabase_admin_request,
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
    resp = supabase_request(
        'GET', 'skills?select=*&order=sort_order.asc,name.asc'
    )
    return {'skills': resp.json() if resp.ok else []}


@jobs_api_bp.route('/api/religions')
@cache_for(seconds=300)
def api_religions():
    """Получить список вероисповеданий (JSON)."""
    resp = supabase_request(
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
    except Exception:
        current_app.logger.error('api_search_jobs ERROR: %s', traceback.format_exc())
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
def invite_worker(job_id, worker_id):
    """Работодатель приглашает трудника на задание."""
    if not check_job_owner(job_id, session['user_id']):
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    # Проверить, не приглашён ли уже
    check = supabase_request(
        'GET',
        f'invitations?job_id=eq.{job_id}&worker_id=eq.{worker_id}&select=id'
    )
    if check.ok and check.json():
        return jsonify({'success': False, 'error': 'Приглашение уже отправлено'}), 409

    # Проверить, есть ли свободные места
    job_resp = supabase_request(
        'GET',
        f'jobs?id=eq.{job_id}&select=current_workers,max_workers,organization_name'
    )
    if job_resp.ok and job_resp.json():
        job = job_resp.json()[0]
        if job['current_workers'] >= job['max_workers']:
            return jsonify({'success': False, 'error': 'Все места заняты'}), 409

    msg = request.get_json(silent=True) or {}
    inv = supabase_request('POST', 'invitations', json={
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
    """JSON API: список приглашений."""
    user_id = session['user_id']
    role = session.get('role', 'worker')
    if role == 'worker':
        resp = supabase_request(
            'GET',
            f'invitations?worker_id=eq.{user_id}&select=*,job:jobs(organization_name,payment_amount)&order=created_at.desc'
        )
    else:
        resp = supabase_request(
            'GET',
            f'invitations?employer_id=eq.{user_id}&select=*,job:jobs(organization_name),worker:profiles!invitations_worker_id_fkey(full_name)&order=created_at.desc'
        )
    return jsonify({'invitations': resp.json() if resp.ok else []})


@jobs_api_bp.route('/api/invitations/<invitation_id>/respond', methods=['POST'])
@login_required
def respond_invitation(invitation_id):
    """Трудник принимает или отклоняет приглашение."""
    data = request.get_json(silent=True) or {}
    action = data.get('action')
    if action not in ('accept', 'reject'):
        return jsonify({'success': False, 'error': 'Укажите действие: accept или reject'}), 400

    if session.get('role') != 'worker':
        return jsonify({'success': False, 'error': 'Только трудник может отвечать на приглашения'}), 403

    inv_resp = supabase_request(
        'GET',
        f'invitations?id=eq.{invitation_id}&select=worker_id,job_id,employer_id,status'
    )
    if not inv_resp.ok or not inv_resp.json():
        return jsonify({'success': False, 'error': 'Приглашение не найдено'}), 404

    inv = inv_resp.json()[0]
    if inv['worker_id'] != session['user_id']:
        return jsonify({'success': False, 'error': 'Нет доступа'}), 403

    if inv['status'] != 'pending':
        return jsonify({'success': False, 'error': f'Приглашение уже {inv["status"]}'}), 409

    new_status = 'accepted' if action == 'accept' else 'rejected'
    supabase_request('PATCH', f'invitations?id=eq.{invitation_id}',
                     json={'status': new_status, 'responded_at': 'now()'})

    if action == 'accept':
        # При принятии приглашения отклик сразу accepted (работодатель уже выбрал трудника)
        supabase_admin_request('POST', 'applications', json={
            'job_id': inv['job_id'],
            'worker_id': inv['worker_id'],
            'status': 'accepted'
        })
        # Обновить счётчик занятых мест (admin_request — worker не может PATCH jobs)
        job_resp = supabase_admin_request(
            'GET',
            f'jobs?id=eq.{inv["job_id"]}&select=current_workers,max_workers,status'
        )
        if job_resp.ok and job_resp.json():
            job = job_resp.json()[0]
            new_count = job['current_workers'] + 1
            new_status_job = 'completed' if new_count >= job['max_workers'] else job['status']
            supabase_admin_request('PATCH', f'jobs?id=eq.{inv["job_id"]}', json={
                'current_workers': new_count,
                'status': new_status_job
            })
        # Уведомить работника о принятии
        notify(inv['worker_id'], 'application_accepted', 'Приглашение принято',
               f'Ваша заявка на задание #{inv["job_id"]} принята.',
               data={'job_id': inv['job_id'],
                     'link': url_for('jobs.job_detail', job_id=inv['job_id'], _external=True)})
        # Уведомить работодателя
        notify(inv['employer_id'], 'application_received', 'Приглашение принято',
               f'Трудник принял ваше приглашение на задание',
               data={'job_id': inv['job_id'],
                     'link': url_for('jobs.job_detail', job_id=inv['job_id'], _external=True)})

    return jsonify({'success': True, 'new_status': new_status})
