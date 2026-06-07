from collections import Counter
from flask import Blueprint, flash, redirect, render_template, request, session, url_for, jsonify

from app.decorators import login_required, role_required
from app.utils import supabase_request

admin_bp = Blueprint('admin', __name__)


def _require_admin():
    """Проверить, что текущий пользователь — админ. Возвращает True/False."""
    resp = supabase_request('GET', f'profiles?id=eq.{session.get("user_id")}&select=role')
    return resp.ok and resp.json() and resp.json()[0].get('role') == 'admin'


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
            query += f'&full_name=ilike.*{search}*'
        if role_filter:
            query += f'&role=eq.{role_filter}'
        query += '&order=created_at.desc'
        users_resp = supabase_request('GET', query)
        users = users_resp.json() if users_resp.ok else []

    # Задания
    jobs = []
    if tab == 'jobs':
        search = request.args.get('search', '')
        status_filter = request.args.get('status', '')
        query = 'jobs?select=*,employer:profiles!employer_id(full_name)&limit=100'
        if search:
            query += f'&organization_name=ilike.*{search}*'
        if status_filter:
            query += f'&status=eq.{status_filter}'
        query += '&order=created_at.desc'
        jobs_resp = supabase_request('GET', query)
        jobs = jobs_resp.json() if jobs_resp.ok else []

    # Верификация
    pending = []
    if tab == 'verification':
        resp = supabase_request('GET', 'profiles?verification_status=eq.pending&select=*')
        pending = resp.json() if resp.ok else []

    return render_template('admin.html',
                           tab=tab, stats=stats, users=users,
                           jobs=jobs, pending=pending)


# ── Управление пользователями ──────────────────────────

@admin_bp.route('/admin/users/<user_id>/role', methods=['POST'])
@login_required
def update_user_role(user_id):
    if not _require_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('admin.admin_panel'))
    new_role = request.form.get('role', '')
    if new_role in ('worker', 'employer', 'admin'):
        supabase_request('PATCH', f'profiles?id=eq.{user_id}', json={'role': new_role})
        flash(f'Роль изменена на {new_role}', 'success')
    else:
        flash('Недопустимая роль', 'danger')
    return redirect(url_for('admin.admin_panel', tab='users'))


@admin_bp.route('/admin/users/<user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    if not _require_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('admin.admin_panel'))
    supabase_request('DELETE', f'profiles?id=eq.{user_id}')
    flash('Пользователь удалён', 'success')
    return redirect(url_for('admin.admin_panel', tab='users'))


# ── Управление заданиями ──────────────────────────

@admin_bp.route('/admin/jobs/<job_id>/status', methods=['POST'])
@login_required
def update_job_status(job_id):
    if not _require_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('admin.admin_panel'))
    new_status = request.form.get('status', '')
    if new_status in ('open', 'in_progress', 'cancelled', 'completed', 'paid'):
        supabase_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': new_status})
        flash(f'Статус задания изменён на {new_status}', 'success')
    return redirect(url_for('admin.admin_panel', tab='jobs'))


@admin_bp.route('/admin/jobs/<job_id>/delete', methods=['POST'])
@login_required
def delete_job_admin(job_id):
    if not _require_admin():
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('admin.admin_panel'))
    supabase_request('DELETE', f'jobs?id=eq.{job_id}')
    flash('Задание удалено', 'success')
    return redirect(url_for('admin.admin_panel', tab='jobs'))


# ── Справочники: навыки и вероисповедания ──────────────

@admin_bp.route('/admin/skills', methods=['GET'])
@login_required
def get_skills():
    if not _require_admin():
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    resp = supabase_request('GET', 'skills?select=*&order=name.asc')
    return jsonify({'success': True, 'skills': resp.json() if resp.ok else []})

@admin_bp.route('/admin/skills', methods=['POST'])
@login_required
def add_skill():
    if not _require_admin():
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    resp = supabase_request('POST', 'skills', json={'name': name})
    if resp.ok:
        return jsonify({'success': True, 'skill': resp.json()[0] if isinstance(resp.json(), list) else resp.json()})
    return jsonify({'success': False, 'error': resp.text}), 400

@admin_bp.route('/admin/skills/<skill_id>', methods=['PUT'])
@login_required
def update_skill(skill_id):
    if not _require_admin():
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    resp = supabase_request('PATCH', f'skills?id=eq.{skill_id}', json={'name': name})
    return jsonify({'success': resp.ok})

@admin_bp.route('/admin/skills/<skill_id>', methods=['DELETE'])
@login_required
def delete_skill(skill_id):
    if not _require_admin():
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    supabase_request('DELETE', f'user_skills?skill_id=eq.{skill_id}')
    supabase_request('DELETE', f'job_skills?skill_id=eq.{skill_id}')
    resp = supabase_request('DELETE', f'skills?id=eq.{skill_id}')
    return jsonify({'success': resp.ok})

@admin_bp.route('/admin/religions', methods=['GET'])
@login_required
def get_religions():
    if not _require_admin():
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    resp = supabase_request('GET', 'religions?select=*&order=name.asc')
    return jsonify({'success': True, 'religions': resp.json() if resp.ok else []})

@admin_bp.route('/admin/religions', methods=['POST'])
@login_required
def add_religion():
    if not _require_admin():
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    resp = supabase_request('POST', 'religions', json={'name': name})
    if resp.ok:
        return jsonify({'success': True, 'religion': resp.json()[0] if isinstance(resp.json(), list) else resp.json()})
    return jsonify({'success': False, 'error': resp.text}), 400

@admin_bp.route('/admin/religions/<religion_id>', methods=['PUT'])
@login_required
def update_religion(religion_id):
    if not _require_admin():
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    resp = supabase_request('PATCH', f'religions?id=eq.{religion_id}', json={'name': name})
    return jsonify({'success': resp.ok})

@admin_bp.route('/admin/religions/<religion_id>', methods=['DELETE'])
@login_required
def delete_religion(religion_id):
    if not _require_admin():
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    resp = supabase_request('DELETE', f'religions?id=eq.{religion_id}')
    return jsonify({'success': resp.ok})

# ── Верификация работодателей ──────────────────────────

@admin_bp.route('/admin/approve/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def approve_employer(user_id):
    supabase_request('PATCH', f'profiles?id=eq.{user_id}',
                     json={'verification_status': 'approved'})
    flash('Работодатель верифицирован', 'success')
    return redirect(url_for('admin.admin_panel', tab='verification'))


@admin_bp.route('/admin/reject/<user_id>', methods=['POST'])
@login_required
@role_required('admin')
def reject_employer(user_id):
    supabase_request('PATCH', f'profiles?id=eq.{user_id}',
                     json={'verification_status': 'rejected'})
    flash('Верификация отклонена', 'warning')
    return redirect(url_for('admin.admin_panel', tab='verification'))
