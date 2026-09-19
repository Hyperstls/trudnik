from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required, validate_uuid
from app.services import favorites_service
from app.utils import postgrest_request
from app.utils.security import safe_redirect

favorites_bp = Blueprint('favorites', __name__)


@favorites_bp.route('/favorites')
@login_required
def favorites():
    """Избранное (мультирольность, 2026-09-03): обе секции для всех —

    - Избранные трудники (когда-то employer-only) — любой может собирать
      исполнителей (например, для повторного найма).
    - Избранные работодатели + задания (когда-то worker-only) — любой
      может собирать «вдохновение»/работодателей для отклика.
    Пустые секции шаблон скрывает сам.
    """
    user_id = session['user_id']
    items = []            # избранные трудники
    employer_items = []   # избранные работодатели
    invited_worker_ids = set()

    # Избранные трудники
    resp = postgrest_request('GET',
        f'favorites?user_id=eq.{user_id}&favorite_type=eq.worker&select=target:profiles!fk_favorites_target_id(id,full_name,photo_url,rating,city,experience,desired_payment)')
    if resp.ok:
        items = [item['target'] for item in resp.json() if item.get('target')]
        if items:
            worker_ids = [item['id'] for item in items if item.get('id')]
            if worker_ids:
                ids_filter = ','.join(worker_ids)
                inv_resp = postgrest_request('GET',
                    f'invitations?employer_id=eq.{user_id}&worker_id=in.({ids_filter})&status=in.(pending,accepted)&select=worker_id')
                if inv_resp.ok and inv_resp.json():
                    invited_worker_ids = {inv['worker_id'] for inv in inv_resp.json()}

    # Избранные работодатели
    resp = postgrest_request('GET',
        f'favorites?user_id=eq.{user_id}&favorite_type=eq.employer&select=target:profiles!fk_favorites_target_id(id,full_name,photo_url,verification_status,city)')
    if resp.ok:
        employer_items = [item['target'] for item in resp.json() if item.get('target')]

    # Избранные задания
    favorite_jobs = []
    job_resp = postgrest_request('GET',
        f'job_favorites?user_id=eq.{user_id}&select=job:jobs(*)')
    if job_resp.ok and job_resp.json():
        favorite_jobs = [j['job'] for j in job_resp.json() if j.get('job')]

    return render_template('favorites.html', items=items,
                           employer_items=employer_items,
                           favorite_jobs=favorite_jobs,
                           invited_worker_ids=invited_worker_ids)


@favorites_bp.route('/favorite/<target_id>', methods=['POST'])
@login_required
@validate_uuid('target_id')
def add_favorite(target_id):
    status, _resp = favorites_service.add_favorite(session['user_id'], 'worker', target_id)
    if status == 'exists':
        flash('Трудник уже в избранном', 'info')
    elif status == 'error':
        flash('Не удалось добавить в избранное', 'danger')
    return safe_redirect('jobs.index')


@favorites_bp.route('/unfavorite/<target_id>', methods=['POST'])
@login_required
@validate_uuid('target_id')
def remove_favorite(target_id):
    favorites_service.remove_favorite(session['user_id'], 'worker', target_id)
    return redirect(url_for('favorites.favorites'))


# ──────────────────────────────────────────────
# API для избранного (JS-фронтенд)
# ──────────────────────────────────────────────

@favorites_bp.route('/api/favorites/add', methods=['POST'])
@login_required
def add_favorite_api():
    data = request.get_json()
    worker_id = data.get('worker_id')

    if not worker_id:
        return jsonify({'success': False, 'error': 'Не указан worker_id'})

    try:
        status, resp = favorites_service.add_favorite(session['user_id'], 'worker', worker_id)
        if status == 'added':
            return jsonify({'success': True, 'message': 'Трудник добавлен в избранное'})
        if status == 'exists':
            return jsonify({'success': True, 'message': 'Трудник уже в избранном'})
        return jsonify({'success': False, 'error': f'Ошибка сервера: {resp.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@favorites_bp.route('/api/favorites/remove', methods=['POST'])
@login_required
def remove_favorite_api():
    data = request.get_json()
    worker_id = data.get('worker_id')

    if not worker_id:
        return jsonify({'success': False, 'error': 'Не указан worker_id'})

    try:
        favorites_service.remove_favorite(session['user_id'], 'worker', worker_id)
        return jsonify({'success': True, 'message': 'Трудник удалён из избранного'})
    except Exception as e:
        current_app.logger.exception("remove_favorite_api error for worker_id=%s", worker_id)
        return jsonify({'success': False, 'error': 'Внутренняя ошибка сервера'})


@favorites_bp.route('/api/favorites/check', methods=['POST'])
@login_required
def check_favorite_api():
    data = request.get_json()
    worker_id = data.get('worker_id')

    if not worker_id:
        return jsonify({'success': False, 'error': 'Не указан worker_id'})

    try:
        is_favorited = favorites_service.check_favorite(session['user_id'], 'worker', worker_id)
        return jsonify({'success': True, 'is_favorited': is_favorited})
    except Exception as e:
        current_app.logger.exception("check_favorite_api error for worker_id=%s", worker_id)
        return jsonify({'success': False, 'error': 'Внутренняя ошибка сервера'})


@favorites_bp.route('/api/favorites/remove-selected', methods=['POST'])
@login_required
def remove_favorites_selected():
    data = request.get_json()
    worker_ids = data.get('worker_ids', [])

    if not worker_ids:
        return jsonify({'success': False, 'error': 'Не указаны worker_ids'})

    try:
        # Batch delete: используем in.() синтаксис PostgREST — Supabase не используется (устарело)
        ids_filter = ','.join(worker_ids)
        resp = postgrest_request('DELETE',
            f'favorites?user_id=eq.{session["user_id"]}&target_id=in.({ids_filter})')
        
        if resp.ok:
            return jsonify({'success': True, 'message': f'{len(worker_ids)} трудников удалено из избранного'})
        else:
            return jsonify({'success': False, 'error': f'Ошибка сервера: {resp.status_code}'}), 400
    except Exception as e:
        current_app.logger.exception("remove_favorites_selected error for worker_ids=%s", worker_ids)
        return jsonify({'success': False, 'error': 'Внутренняя ошибка сервера'}), 500
