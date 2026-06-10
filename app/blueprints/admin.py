from collections import Counter
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for, jsonify
import requests

from app.decorators import login_required, role_required
from app.utils import sanitize_postgrest, supabase_request, supabase_admin_request, SUPABASE_URL, SUPABASE_KEY, SERVICE_KEY

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin')
@login_required
@role_required('admin')
def admin_panel():
    """Админ-панель: дашборд, пользователи, задания, верификация."""
    tab = request.args.get('tab', 'dashboard')

    # Дашборд: базовая статистика
    stats = {}
    if tab == 'dashboard':
        users_resp = supabase_request('GET', 'profiles?select=role&limit=1000')
        if users_resp.ok and users_resp.json():
            roles = Counter(u['role'] for u in users_resp.json())
            stats['total_users'] = sum(roles.values())
            stats['workers'] = roles.get('worker', 0)
            stats['employers'] = roles.get('employer', 0)
            stats['admins'] = roles.get('admin', 0)

        jobs_resp = supabase_request('GET', 'jobs?select=status&limit=1000')
        if jobs_resp.ok and jobs_resp.json():
            statuses = Counter(j['status'] for j in jobs_resp.json())
            stats['total_jobs'] = sum(statuses.values())
            stats['open_jobs'] = statuses.get('open', 0)
            stats['in_progress_jobs'] = statuses.get('in_progress', 0)
            stats['completed_jobs'] = statuses.get('completed', 0) + statuses.get('paid', 0)

        payments_resp = supabase_request('GET', 'contact_payments?select=status,amount&limit=1000')
        if payments_resp.ok and payments_resp.json():
            payments = payments_resp.json()
            stats['total_payments'] = len(payments)
            stats['paid_payments'] = sum(1 for p in payments if p.get('status') == 'paid')
            stats['total_revenue'] = sum(p.get('amount', 0) for p in payments if p.get('status') == 'paid')

        pending_resp = supabase_request('GET', 'profiles?verification_status=eq.pending&select=id')
        stats['pending_verifications'] = len(pending_resp.json()) if pending_resp.ok and pending_resp.json() else 0

    # Пользователи
    users = []
    if tab == 'users':
        search = request.args.get('search', '')
        role_filter = request.args.get('role', '')
        query = 'profiles?select=*&limit=100'
        if search:
            query += f'&full_name=ilike.*{sanitize_postgrest(search)}*'
        if role_filter:
            query += f'&role=eq.{sanitize_postgrest(role_filter)}'
        query += '&order=full_name.asc'
        users_resp = supabase_request('GET', query)
        users = users_resp.json() if users_resp.ok else []

    # Задания
    jobs = []
    if tab == 'jobs':
        search = request.args.get('search', '')
        status_filter = request.args.get('status', '')
        query = 'jobs?select=*,employer:profiles!employer_id(full_name)&limit=100'
        if search:
            query += f'&organization_name=ilike.*{sanitize_postgrest(search)}*'
        if status_filter:
            query += f'&status=eq.{sanitize_postgrest(status_filter)}'
        query += '&order=created_at.desc'
        jobs_resp = supabase_request('GET', query)
        jobs = jobs_resp.json() if jobs_resp.ok else []

    # Верификация — все работодатели с любым статусом
    pending = []
    verified = []
    if tab == 'verification':
        resp = supabase_request('GET', 'profiles?verification_status=not.is.null&select=*&order=updated_at.desc&limit=50')
        all_verify = resp.json() if resp.ok else []
        pending = [u for u in all_verify if u.get('verification_status') == 'pending']
        verified = [u for u in all_verify if u.get('verification_status') in ('approved', 'rejected')]

    return render_template('admin.html',
                           tab=tab, stats=stats, users=users,
                           jobs=jobs, pending=pending, verified=verified)


# ── Управление пользователями ──────────────────────────

@admin_bp.route('/admin/users/<user_id>/role', methods=['POST'])
@login_required
@role_required('admin')
def update_user_role(user_id):
    new_role = request.form.get('role', '')
    if new_role in ('worker', 'employer', 'admin'):
        supabase_request('PATCH', f'profiles?id=eq.{user_id}', json={'role': new_role})
        flash(f'Роль изменена на {new_role}', 'success')
    else:
        flash('Недопустимая роль', 'danger')
    return redirect(url_for('admin.admin_panel', tab='users'))


@admin_bp.route('/admin/users/<user_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_user(user_id):
    # 1. Получить информацию о пользователе (роль, employer_id для заданий)
    profile_resp = supabase_admin_request('GET', f'profiles?id=eq.{user_id}&select=id,role')
    if not profile_resp.ok or not profile_resp.json():
        flash('Пользователь не найден', 'danger')
        return redirect(url_for('admin.admin_panel', tab='users'))
    user_profile = profile_resp.json()[0]
    user_role = user_profile.get('role', '')

    # 2. Если пользователь — работодатель, удалить все его задания (с каскадным удалением)
    if user_role == 'employer':
        jobs_resp = supabase_admin_request('GET', f'jobs?employer_id=eq.{user_id}&select=id')
        if jobs_resp.ok and jobs_resp.json():
            for job in jobs_resp.json():
                _delete_job_cascade(job['id'])

    # 3. Каскадное удаление связанных записей
    cascade_tables = [
        ('applications', f'worker_id=eq.{user_id}'),
        ('notifications', f'user_id=eq.{user_id}'),
        ('favorites', f'user_id=eq.{user_id}'),
        ('favorites', f'favorite_user_id=eq.{user_id}'),
        ('job_favorites', f'user_id=eq.{user_id}'),
        ('blacklists', f'user_id=eq.{user_id}'),
        ('blacklists', f'blocked_user_id=eq.{user_id}'),
        ('ratings', f'rater_user_id=eq.{user_id}'),
        ('ratings', f'rated_user_id=eq.{user_id}'),
        ('invitations', f'employer_id=eq.{user_id}'),
        ('invitations', f'worker_id=eq.{user_id}'),
        ('user_skills', f'user_id=eq.{user_id}'),
        ('shifts', f'worker_id=eq.{user_id}'),
        ('shifts', f'employer_id=eq.{user_id}'),
        ('hires', f'employer_id=eq.{user_id}'),
        ('hires', f'worker_id=eq.{user_id}'),
        ('contact_payments', f'employer_id=eq.{user_id}'),
        ('contact_payments', f'worker_id=eq.{user_id}'),
        ('push_subscriptions', f'user_id=eq.{user_id}'),
        ('messages', f'sender_id=eq.{user_id}'),
        ('messages', f'receiver_id=eq.{user_id}'),
        ('monetization_settings', None),  # не привязана к пользователю
    ]
    for table, condition in cascade_tables:
        if condition:
            supabase_admin_request('DELETE', f'{table}?{condition}')

    # 4. Удалить профиль из public.profiles
    profile_del = supabase_admin_request('DELETE', f'profiles?id=eq.{user_id}')
    if not profile_del.ok:
        current_app.logger.error(f"Admin delete user: failed to delete profile {user_id}: {profile_del.status_code} {profile_del.text}")
        flash('Ошибка при удалении пользователя', 'danger')
        return redirect(url_for('admin.admin_panel', tab='users'))

    # 5. Удалить пользователя из auth.users (через Admin API)
    if SERVICE_KEY:
        auth_url = f'{SUPABASE_URL}/auth/v1/admin/users/{user_id}'
        auth_headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SERVICE_KEY}',
            'Content-Type': 'application/json',
        }
        try:
            auth_resp = requests.delete(auth_url, headers=auth_headers, timeout=15)
            if not auth_resp.ok:
                current_app.logger.warning(
                    f"Admin delete user: auth.users delete returned {auth_resp.status_code} for {user_id}. "
                    f"Profile was deleted but auth entry may remain."
                )
        except requests.RequestException as e:
            current_app.logger.error(f"Admin delete user: auth.users request failed for {user_id}: {e}")

    flash('Пользователь удалён', 'success')
    return redirect(url_for('admin.admin_panel', tab='users'))


# ── Управление заданиями ──────────────────────────

@admin_bp.route('/admin/jobs/<job_id>/status', methods=['POST'])
@login_required
@role_required('admin')
def update_job_status(job_id):
    new_status = request.form.get('status', '')
    if new_status in ('open', 'in_progress', 'cancelled', 'completed', 'paid'):
        supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': new_status})
        flash(f'Статус задания изменён на {new_status}', 'success')
    return redirect(url_for('admin.admin_panel', tab='jobs'))


@admin_bp.route('/admin/jobs/<job_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_job_admin(job_id):
    _delete_job_cascade(job_id)
    flash('Задание удалено', 'success')
    return redirect(url_for('admin.admin_panel', tab='jobs'))


def _delete_job_cascade(job_id):
    """Каскадное удаление задания и всех связанных записей (через service role key)."""
    cascade_tables = [
        ('applications', f'job_id=eq.{job_id}'),
        ('job_skills', f'job_id=eq.{job_id}'),
        ('job_photos', f'job_id=eq.{job_id}'),
        ('job_favorites', f'job_id=eq.{job_id}'),
        ('shifts', f'job_id=eq.{job_id}'),
        ('contact_payments', f'job_id=eq.{job_id}'),
        ('invitations', f'job_id=eq.{job_id}'),
    ]
    for table, condition in cascade_tables:
        supabase_admin_request('DELETE', f'{table}?{condition}')

    # Уведомления, связанные с заданием
    supabase_admin_request('DELETE', f'notifications?job_id=eq.{job_id}')

    # Само задание
    job_del = supabase_admin_request('DELETE', f'jobs?id=eq.{job_id}')
    if not job_del.ok:
        current_app.logger.error(f"Admin delete job: failed to delete job {job_id}: {job_del.status_code} {job_del.text}")


# ── Справочники: навыки и вероисповедания ──────────────

@admin_bp.route('/admin/skills', methods=['GET'])
@login_required
@role_required('admin')
def get_skills():
    # Пробуем сортировку по sort_order; если колонки нет — fallback на name
    resp = supabase_request('GET', 'skills?select=*&order=sort_order.asc,name.asc')
    if not resp.ok:
        resp = supabase_request('GET', 'skills?select=*&order=name.asc')
    return jsonify({'success': True, 'skills': resp.json() if resp.ok else []})

@admin_bp.route('/admin/skills', methods=['POST'])
@login_required
@role_required('admin')
def add_skill():
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    # Находим максимальный sort_order (если колонка есть) и добавляем +1
    max_order = 0
    existing = supabase_request('GET', 'skills?select=sort_order&order=sort_order.desc&limit=1')
    if not existing.ok:
        existing = supabase_request('GET', 'skills?select=id&order=name.desc&limit=1')
    if existing.ok and existing.json():
        item = existing.json()[0] if existing.json() else {}
        max_order = item.get('sort_order', 0)
    resp = supabase_request('POST', 'skills', json={'name': name, 'sort_order': max_order + 1})
    if resp.ok:
        return jsonify({'success': True, 'skill': resp.json()[0] if isinstance(resp.json(), list) else resp.json()})
    return jsonify({'success': False, 'error': resp.text}), 400

@admin_bp.route('/admin/skills/reorder', methods=['POST'])
@login_required
@role_required('admin')
def reorder_skills():
    """Принять новый порядок навыков: массив [{id, sort_order}, ...]"""
    data = request.get_json() or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'error': 'items required'}), 400
    for item in items:
        supabase_request('PATCH', f'skills?id=eq.{item["id"]}', json={'sort_order': item['sort_order']})
    return jsonify({'success': True})

@admin_bp.route('/admin/skills/<skill_id>', methods=['PUT'])
@login_required
@role_required('admin')
def update_skill(skill_id):
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    resp = supabase_request('PATCH', f'skills?id=eq.{skill_id}', json={'name': name})
    return jsonify({'success': resp.ok})

@admin_bp.route('/admin/skills/<skill_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_skill(skill_id):
    supabase_request('DELETE', f'user_skills?skill_id=eq.{skill_id}')
    supabase_request('DELETE', f'job_skills?skill_id=eq.{skill_id}')
    resp = supabase_request('DELETE', f'skills?id=eq.{skill_id}')
    return jsonify({'success': resp.ok})

@admin_bp.route('/admin/religions', methods=['GET'])
@login_required
@role_required('admin')
def get_religions():
    resp = supabase_request('GET', 'religions?select=*&order=sort_order.asc,name.asc')
    if not resp.ok:
        resp = supabase_request('GET', 'religions?select=*&order=name.asc')
    return jsonify({'success': True, 'religions': resp.json() if resp.ok else []})

@admin_bp.route('/admin/religions', methods=['POST'])
@login_required
@role_required('admin')
def add_religion():
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    max_order = 0
    existing = supabase_request('GET', 'religions?select=sort_order&order=sort_order.desc&limit=1')
    if not existing.ok:
        existing = supabase_request('GET', 'religions?select=id&order=name.desc&limit=1')
    if existing.ok and existing.json():
        item = existing.json()[0] if existing.json() else {}
        max_order = item.get('sort_order', 0)
    resp = supabase_request('POST', 'religions', json={'name': name, 'sort_order': max_order + 1})
    if resp.ok:
        return jsonify({'success': True, 'religion': resp.json()[0] if isinstance(resp.json(), list) else resp.json()})
    return jsonify({'success': False, 'error': resp.text}), 400

@admin_bp.route('/admin/religions/reorder', methods=['POST'])
@login_required
@role_required('admin')
def reorder_religions():
    """Принять новый порядок вероисповеданий: массив [{id, sort_order}, ...]"""
    data = request.get_json() or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'error': 'items required'}), 400
    for item in items:
        supabase_request('PATCH', f'religions?id=eq.{item["id"]}', json={'sort_order': item['sort_order']})
    return jsonify({'success': True})

@admin_bp.route('/admin/religions/<religion_id>', methods=['PUT'])
@login_required
@role_required('admin')
def update_religion(religion_id):
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    resp = supabase_request('PATCH', f'religions?id=eq.{religion_id}', json={'name': name})
    return jsonify({'success': resp.ok})

@admin_bp.route('/admin/religions/<religion_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_religion(religion_id):
    resp = supabase_request('DELETE', f'religions?id=eq.{religion_id}')
    return jsonify({'success': resp.ok})

# ── Верификация работодателей ──────────────────────────

@admin_bp.route('/admin/approve/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def approve_employer(user_id):
    resp = supabase_request('PATCH', f'profiles?id=eq.{user_id}',
                     json={'verification_status': 'approved'})
    if resp and resp.ok:
        flash('Работодатель верифицирован', 'success')
    else:
        flash('Ошибка при верификации', 'danger')
    return redirect(url_for('admin.admin_panel', tab='verification'))


@admin_bp.route('/admin/reject/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def reject_employer(user_id):
    resp = supabase_request('PATCH', f'profiles?id=eq.{user_id}',
                     json={'verification_status': 'rejected'})
    if resp and resp.ok:
        flash('Верификация отклонена', 'warning')
    else:
        flash('Ошибка при отклонении', 'danger')
    return redirect(url_for('admin.admin_panel', tab='verification'))
