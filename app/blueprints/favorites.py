from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.utils import supabase_request

favorites_bp = Blueprint('favorites', __name__)


@favorites_bp.route('/favorites')
@login_required
def favorites():
    resp = supabase_request('GET',
        f'favorites?user_id=eq.{session["user_id"]}&select=target:profiles!favorites_target_id_fkey(id,full_name,photo_url,rating,city,skills,experience,desired_payment)')
    items = [item['target'] for item in resp.json()] if resp.ok else []

    favorite_jobs = []
    if session.get('role') == 'worker':
        job_resp = supabase_request('GET',
            f'job_favorites?user_id=eq.{session["user_id"]}&select=job:jobs(*)')
        if job_resp.ok and job_resp.json():
            favorite_jobs = [j['job'] for j in job_resp.json() if j.get('job')]

    return render_template('favorites.html', items=items, favorite_jobs=favorite_jobs)


@favorites_bp.route('/favorite/<target_id>', methods=['POST'])
@login_required
def add_favorite(target_id):
    resp = supabase_request('POST', 'favorites', json={'user_id': session['user_id'], 'target_id': target_id})
    if not resp.ok:
        flash('Не удалось добавить в избранное', 'danger')
    return redirect(request.referrer or url_for('jobs.index'))


@favorites_bp.route('/unfavorite/<target_id>', methods=['POST'])
@login_required
def remove_favorite(target_id):
    supabase_request('DELETE', f'favorites?user_id=eq.{session["user_id"]}&target_id=eq.{target_id}')
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
        resp = supabase_request('POST', 'favorites', json={'user_id': session['user_id'], 'target_id': worker_id})
        if resp.ok:
            return jsonify({'success': True, 'message': 'Трудник добавлен в избранное'})
        else:
            # Проверяем на дубликат
            error_text = resp.text if hasattr(resp, 'text') else ''
            if 'duplicate' in error_text.lower() or resp.status_code == 409:
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
        supabase_request('DELETE', f'favorites?user_id=eq.{session["user_id"]}&target_id=eq.{worker_id}')
        return jsonify({'success': True, 'message': 'Трудник удалён из избранного'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@favorites_bp.route('/api/favorites/check', methods=['POST'])
@login_required
def check_favorite_api():
    data = request.get_json()
    worker_id = data.get('worker_id')

    if not worker_id:
        return jsonify({'success': False, 'error': 'Не указан worker_id'})

    try:
        resp = supabase_request('GET', f'favorites?user_id=eq.{session["user_id"]}&target_id=eq.{worker_id}')
        is_favorited = resp.ok and len(resp.json()) > 0
        return jsonify({'success': True, 'is_favorited': is_favorited})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@favorites_bp.route('/api/favorites/remove-selected', methods=['POST'])
@login_required
def remove_favorites_selected():
    data = request.get_json()
    worker_ids = data.get('worker_ids', [])

    if not worker_ids:
        return jsonify({'success': False, 'error': 'Не указаны worker_ids'})

    try:
        # Batch delete: используем in.() синтаксис Supabase
        ids_filter = ','.join(worker_ids)
        resp = supabase_request('DELETE',
            f'favorites?user_id=eq.{session["user_id"]}&target_id=in.({ids_filter})')
        
        if resp.ok:
            return jsonify({'success': True, 'message': f'{len(worker_ids)} трудников удалено из избранного'})
        else:
            return jsonify({'success': False, 'error': f'Ошибка сервера: {resp.status_code}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
