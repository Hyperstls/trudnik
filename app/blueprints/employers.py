from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from app.decorators import login_required
from app.utils import supabase_request, sanitize_postgrest

employers_bp = Blueprint('employers', __name__)


@employers_bp.route('/employers')
@login_required
def employers_list():
    """Список всех работодателей с пагинацией, поиском и фильтрацией."""
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 20
    city = request.args.get('city', '')
    skills = request.args.get('skills', '')
    search = request.args.get('q', '')

    # Базовый запрос: только работодатели
    query = 'role=eq.employer'
    if city:
        query += f'&city=ilike.*{sanitize_postgrest(city)}*'
    if search:
        query += f'&full_name=ilike.*{sanitize_postgrest(search)}*'
    query += '&select=id,full_name,photo_url,rating,total_reviews,city,verification_status,bio'
    query += '&order=rating.desc'

    # Пагинация
    offset = (page - 1) * per_page
    query += f'&limit={per_page}&offset={offset}'

    resp = supabase_request('GET', f'profiles?{query}', headers={'Prefer': 'count=exact'})
    employers = resp.json() if resp.ok and resp.json() else []

    # Фильтрация: исключаем работодателей, заблокировавших текущего трудника
    if session.get('role') == 'worker' and session.get('user_id'):
        bl_resp = supabase_request('GET',
            f'blacklists?blocked_user_id=eq.{session["user_id"]}&select=user_id')
        if bl_resp.ok and bl_resp.json():
            blocked_employer_ids = {b['user_id'] for b in bl_resp.json()}
            employers = [e for e in employers if e['id'] not in blocked_employer_ids]

    # Подсчёт открытых заданий для каждого работодателя
    open_jobs_counts = {}
    if employers:
        ids = ','.join(e['id'] for e in employers)
        jobs_resp = supabase_request('GET',
            f'jobs?employer_id=in.({ids})&status=eq.open&select=employer_id')
        if jobs_resp.ok and jobs_resp.json():
            for job in jobs_resp.json():
                eid = job['employer_id']
                open_jobs_counts[eid] = open_jobs_counts.get(eid, 0) + 1

    # Проверка избранного (только для трудников)
    favorited_ids = set()
    if session.get('user_id') and session.get('role') == 'worker':
        fav_resp = supabase_request('GET',
            f'favorites?user_id=eq.{session["user_id"]}&favorite_type=eq.employer&select=target_id')
        if fav_resp.ok and fav_resp.json():
            favorited_ids = {f['target_id'] for f in fav_resp.json()}

    # Определяем total_pages из заголовка content-range
    total_count = len(employers)
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    return render_template('employers.html',
                           employers=employers,
                           favorited_employer_ids=favorited_ids,
                           open_jobs_counts=open_jobs_counts,
                           page=page,
                           total_pages=total_pages,
                           city=city,
                           search=search)


@employers_bp.route('/employers/<employer_id>')
@login_required
def employer_detail(employer_id):
    """Профиль работодателя + его открытые задания."""
    user_id = session.get('user_id')

    # Запрос профиля
    profile_resp = supabase_request('GET',
        f'profiles?id=eq.{employer_id}&select=*')
    if not profile_resp.ok or not profile_resp.json():
        flash('Работодатель не найден', 'danger')
        return redirect(url_for('employers.employers_list'))

    employer = profile_resp.json()[0]
    if employer.get('role') != 'employer':
        flash('Работодатель не найден', 'danger')
        return redirect(url_for('employers.employers_list'))

    # Открытые задания работодателя
    # Если текущий трудник заблокирован этим работодателем — скрываем задания
    open_jobs = []
    if session.get('role') == 'worker' and session.get('user_id'):
        bl_check = supabase_request('GET',
            f'blacklists?user_id=eq.{employer_id}&blocked_user_id=eq.{session["user_id"]}&select=user_id')
        is_blocked = bl_check.ok and len(bl_check.json() or []) > 0
    else:
        is_blocked = False

    if not is_blocked:
        jobs_resp = supabase_request('GET',
            f'jobs?employer_id=eq.{employer_id}&status=eq.open&select=*,photos:job_photos(*)&order=created_at.desc')
        open_jobs = jobs_resp.json() if jobs_resp.ok and jobs_resp.json() else []

    # Проверка избранного и откликов
    is_favorited = False
    already_applied_job_ids = set()
    if session.get('role') == 'worker':
        fav_resp = supabase_request('GET',
            f'favorites?user_id=eq.{user_id}&target_id=eq.{employer_id}&favorite_type=eq.employer')
        is_favorited = fav_resp.ok and len(fav_resp.json() or []) > 0

        if open_jobs:
            job_ids = ','.join(j['id'] for j in open_jobs)
            app_resp = supabase_request('GET',
                f'applications?worker_id=eq.{user_id}&job_id=in.({job_ids})&select=job_id')
            if app_resp.ok and app_resp.json():
                already_applied_job_ids = {a['job_id'] for a in app_resp.json()}

    return render_template('employer_detail.html',
                           employer=employer,
                           open_jobs=open_jobs,
                           is_favorited=is_favorited,
                           already_applied_job_ids=already_applied_job_ids)


@employers_bp.route('/employers/<employer_id>/favorite', methods=['POST'])
@login_required
def toggle_favorite(employer_id):
    """Toggle избранного работодателя (form-based)."""
    user_id = session['user_id']

    try:
        check = supabase_request('GET',
            f'favorites?user_id=eq.{user_id}&target_id=eq.{employer_id}&favorite_type=eq.employer')
        is_favorited = check.ok and len(check.json() or []) > 0

        if is_favorited:
            supabase_request('DELETE',
                f'favorites?user_id=eq.{user_id}&target_id=eq.{employer_id}&favorite_type=eq.employer')
            flash('Работодатель удалён из избранного', 'success')
        else:
            supabase_request('POST', 'favorites', json={
                'user_id': user_id,
                'target_id': employer_id,
                'favorite_type': 'employer'
            })
            flash('Работодатель добавлен в избранное', 'success')
    except Exception as e:
        current_app.logger.error(f"toggle_favorite error: {e}")
        flash('Произошла ошибка при обновлении избранного', 'danger')
        return redirect(request.referrer or url_for('employers.employers_list'))

    return redirect(request.referrer or url_for('employers.employers_list'))


# ──────────────────────────────────────────────
# API для избранного работодателей (JS-фронтенд)
# ──────────────────────────────────────────────

@employers_bp.route('/api/employers/favorites/add', methods=['POST'])
@login_required
def add_employer_favorite_api():
    data = request.get_json()
    employer_id = data.get('employer_id')

    if not employer_id:
        return jsonify({'success': False, 'error': 'Не указан employer_id'})

    try:
        resp = supabase_request('POST', 'favorites', json={
            'user_id': session['user_id'],
            'target_id': employer_id,
            'favorite_type': 'employer'
        })
        if resp.ok:
            return jsonify({'success': True, 'message': 'Работодатель добавлен в избранное'})
        else:
            error_text = resp.text if hasattr(resp, 'text') else ''
            if 'duplicate' in error_text.lower() or resp.status_code == 409:
                return jsonify({'success': True, 'message': 'Работодатель уже в избранном'})
            return jsonify({'success': False, 'error': f'Ошибка сервера: {resp.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@employers_bp.route('/api/employers/favorites/remove', methods=['POST'])
@login_required
def remove_employer_favorite_api():
    data = request.get_json()
    employer_id = data.get('employer_id')

    if not employer_id:
        return jsonify({'success': False, 'error': 'Не указан employer_id'})

    try:
        resp = supabase_request('DELETE',
            f'favorites?user_id=eq.{session["user_id"]}&target_id=eq.{employer_id}&favorite_type=eq.employer')
        if resp.ok:
            return jsonify({'success': True, 'message': 'Работодатель удалён из избранного'})
        else:
            current_app.logger.error(
                f"remove_employer_favorite_api: DELETE failed status={resp.status_code} body={resp.text}"
            )
            return jsonify({'success': False, 'error': f'Ошибка сервера: {resp.status_code}'})
    except Exception as e:
        current_app.logger.error(f"remove_employer_favorite_api exception: {e}")
        return jsonify({'success': False, 'error': str(e)})


@employers_bp.route('/api/employers/favorites/check', methods=['POST'])
@login_required
def check_employer_favorite_api():
    data = request.get_json()
    employer_id = data.get('employer_id')

    if not employer_id:
        return jsonify({'success': False, 'error': 'Не указан employer_id'})

    try:
        resp = supabase_request('GET',
            f'favorites?user_id=eq.{session["user_id"]}&target_id=eq.{employer_id}&favorite_type=eq.employer')
        is_favorited = resp.ok and len(resp.json() or []) > 0
        return jsonify({'success': True, 'is_favorited': is_favorited})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
