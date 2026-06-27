from datetime import datetime
import os
import subprocess
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for, jsonify

from app.decorators import login_required, role_required, admin_required, handle_errors
from app.utils import cache_for, sanitize_postgrest, postgrest_request, postgrest_admin_request, postgrest_rpc, is_circuit_open
from app.utils.helpers import assert_postgrest_ok

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/api/health')
def health_check():
    """Health check endpoint для мониторинга."""
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})


@admin_bp.route('/admin')
@login_required
@admin_required
def admin_panel():
    """Админ-панель: дашборд, пользователи, задания, верификация."""
    tab = request.args.get('tab', 'dashboard')

    # Дашборд: базовая статистика (точные счётчики через count=exact с limit=0)
    stats = {}
    if tab == 'dashboard':
        # Точный подсчёт пользователей по ролям через count=exact
        users_resp = postgrest_admin_request('GET',
            'profiles?select=role&limit=0',
            headers={'Prefer': 'count=exact'})
        if users_resp.ok:
            total_users = 0
            content_range = users_resp.headers.get('Content-Range', '')
            if '/' in content_range:
                total_users = int(content_range.split('/')[-1])
            stats['total_users'] = total_users

        # Считаем по ролям отдельными запросами count=exact
        for role_key in ['worker', 'employer', 'admin']:
            role_resp = postgrest_admin_request('GET',
                f'profiles?role=eq.{role_key}&select=id&limit=0',
                headers={'Prefer': 'count=exact'})
            if role_resp.ok:
                cr = role_resp.headers.get('Content-Range', '')
                if '/' in cr:
                    stats[f'{role_key}s'] = int(cr.split('/')[-1])
            else:
                stats[f'{role_key}s'] = 0

        # Точный подсчёт заданий по статусам через count=exact
        jobs_resp = postgrest_admin_request('GET',
            'jobs?select=status&limit=0',
            headers={'Prefer': 'count=exact'})
        if jobs_resp.ok:
            total_jobs = 0
            content_range = jobs_resp.headers.get('Content-Range', '')
            if '/' in content_range:
                total_jobs = int(content_range.split('/')[-1])
            stats['total_jobs'] = total_jobs

        for status_key in ['open', 'completed', 'cancelled']:
            status_resp = postgrest_admin_request('GET',
                f'jobs?status=eq.{status_key}&select=id&limit=0',
                headers={'Prefer': 'count=exact'})
            if status_resp.ok:
                cr = status_resp.headers.get('Content-Range', '')
                if '/' in cr:
                    stats[f'{status_key}_jobs'] = int(cr.split('/')[-1])
            else:
                stats[f'{status_key}_jobs'] = 0

        pending_resp = postgrest_admin_request('GET',
            'profiles?verification_status=eq.pending&select=id&limit=0',
            headers={'Prefer': 'count=exact'})
        if pending_resp.ok:
            cr = pending_resp.headers.get('Content-Range', '')
            if '/' in cr:
                stats['pending_verifications'] = int(cr.split('/')[-1])
            else:
                stats['pending_verifications'] = 0
        else:
            stats['pending_verifications'] = 0

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
        users_resp = postgrest_admin_request('GET', query)
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
        jobs_resp = postgrest_admin_request('GET', query)
        jobs = jobs_resp.json() if jobs_resp.ok else []
        # Безопасно извлекаем employer_name из встроенного employer (может быть list или dict)
        for j in jobs:
            emp = j.get('employer')
            if emp and isinstance(emp, list) and len(emp) > 0:
                j['employer_name'] = emp[0].get('full_name', '—')
            elif emp and isinstance(emp, dict):
                j['employer_name'] = emp.get('full_name', '—')
            else:
                j['employer_name'] = '—'

    # Верификация — все работодатели с любым статусом
    pending = []
    verified = []
    if tab == 'verification':
        resp = postgrest_admin_request('GET', 'profiles?verification_status=not.is.null&select=*&order=updated_at.desc&limit=50')
        all_verify = resp.json() if resp.ok else []
        pending = [u for u in all_verify if u.get('verification_status') == 'pending']
        verified = [u for u in all_verify if u.get('verification_status') in ('approved', 'rejected')]

    # Справочники: навыки и вероисповедания
    skills = []
    religions = []
    if tab == 'dictionaries' or tab == 'skills' or tab == 'religions':
        skills_resp = postgrest_admin_request('GET', 'skills?select=*&order=sort_order.asc,name.asc')
        skills = skills_resp.json() if skills_resp.ok else []
        religions_resp = postgrest_admin_request('GET', 'religions?select=*&order=sort_order.asc,name.asc')
        religions = religions_resp.json() if religions_resp.ok else []

    # Актуальная версия из VERSION-файла или git (для кнопки «Текущая версия»)
    try:
        version_file = os.path.join(current_app.root_path, 'VERSION')
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                actual_version = f.read().strip()
        else:
            actual_version = subprocess.check_output(
                ['git', 'log', '-1', '--format=%h %s (%ai)'],
                cwd=current_app.root_path, text=True
            ).strip()
    except Exception:
        actual_version = 'dev'

    return render_template('admin.html',
                           tab=tab, stats=stats, users=users,
                           jobs=jobs, pending=pending, verified=verified,
                           skills=skills, religions=religions,
                           actual_version=actual_version)


# ── Управление пользователями ──────────────────────────

@admin_bp.route('/admin/users/<user_id>/role', methods=['POST'])
@login_required
@admin_required
def update_user_role(user_id):
    # Защита: нельзя изменить свою роль (само-лок-аут)
    if user_id == session.get('user_id'):
        flash('Нельзя изменить свою роль', 'danger')
        return redirect(url_for('admin.admin_panel', tab='users'))

    # Защита: нельзя изменить роль другого администратора
    target_resp = postgrest_admin_request('GET', f'profiles?id=eq.{user_id}&select=role')
    if target_resp.ok and target_resp.json():
        target_role = target_resp.json()[0].get('role', '')
        if target_role == 'admin':
            flash('Нельзя изменить роль другого администратора', 'danger')
            return redirect(url_for('admin.admin_panel', tab='users'))

    new_role = request.form.get('role', '')
    if new_role in ('worker', 'employer', 'admin'):
        resp = postgrest_request('PATCH', f'profiles?id=eq.{user_id}', json={'role': new_role})
        if assert_postgrest_ok(resp, 'смена роли пользователя'):
            flash(f'Роль изменена на {new_role}', 'success')
    else:
        flash('Недопустимая роль', 'danger')
    return redirect(url_for('admin.admin_panel', tab='users'))


@admin_bp.route('/admin/users/<user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    # 1. Каскадное удаление пользователя через RPC (этап 4.4)
    rpc_result = postgrest_rpc('delete_user_cascade', {'p_user_id': user_id}, use_admin=True)
    if not rpc_result.ok:
        current_app.logger.error(
            "Admin delete user RPC: failed for %s: status=%s text=%s",
            user_id, rpc_result.status_code, (rpc_result.text or '')[:200]
        )
    result_data = rpc_result.json() if rpc_result.ok else {}
    if not result_data.get('success'):
        flash('Ошибка при удалении пользователя', 'danger')
        return redirect(url_for('admin.admin_panel', tab='users'))

    # Amvera: удаление из auth.users не требуется — Supabase Auth не используется (устарело)
    # Пользователь удалён каскадно через RPC delete_user_cascade

    flash('Пользователь удалён', 'success')
    return redirect(url_for('admin.admin_panel', tab='users'))


# ── Управление заданиями ──────────────────────────

@admin_bp.route('/admin/jobs/<job_id>/status', methods=['POST'])
@login_required
@admin_required
def update_job_status(job_id):
    new_status = request.form.get('status', '')
    if new_status in ('open', 'completed', 'cancelled'):
        resp = postgrest_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': new_status})
        if assert_postgrest_ok(resp, 'изменение статуса задания'):
            flash(f'Статус задания изменён на {new_status}', 'success')
    return redirect(url_for('admin.admin_panel', tab='jobs'))


@admin_bp.route('/admin/jobs/<job_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_job_admin(job_id):
    _delete_job_cascade(job_id)
    flash('Задание удалено', 'success')
    return redirect(url_for('admin.admin_panel', tab='jobs'))


def _delete_job_cascade(job_id):
    """Каскадное удаление задания и всех связанных записей через RPC (этап 4.4)."""
    rpc_result = postgrest_rpc('delete_job_cascade', {'p_job_id': job_id}, use_admin=True)
    if not rpc_result.ok:
        current_app.logger.error(
            "Admin delete job RPC: failed for %s: status=%s text=%s",
            job_id, rpc_result.status_code, (rpc_result.text or '')[:200]
        )


# ── Массовое удаление ────────────────────────────────

@admin_bp.route('/admin/bulk-delete-users', methods=['POST'])
@login_required
@admin_required
def bulk_delete_users():
    """Массовое удаление пользователей (до 20 за раз)."""
    data = request.get_json(silent=True) or {}
    user_ids = data.get('user_ids', [])

    if not isinstance(user_ids, list) or len(user_ids) == 0:
        return jsonify({'deleted': 0, 'failed': 0, 'errors': ['No user_ids provided']}), 400
    if len(user_ids) > 20:
        return jsonify({'deleted': 0, 'failed': len(user_ids), 'errors': ['Max 20 users per request']}), 400

    deleted = 0
    failed = 0
    errors = []

    for user_id in user_ids:
        # 1. Каскадное удаление через RPC
        rpc_result = postgrest_rpc('delete_user_cascade', {'p_user_id': user_id}, use_admin=True)
        if not rpc_result.ok:
            current_app.logger.error(
                "Bulk delete user RPC: failed for %s: status=%s text=%s",
                user_id, rpc_result.status_code, (rpc_result.text or '')[:200]
            )
        result_data = rpc_result.json() if rpc_result.ok else {}
        if not result_data.get('success'):
            failed += 1
            errors.append(f'RPC failed for {user_id}')
            continue

        # Amvera: удаление из auth.users не требуется — Supabase Auth не используется (устарело)
        # Пользователь удалён каскадно через RPC delete_user_cascade

        deleted += 1

    return jsonify({'deleted': deleted, 'failed': failed, 'errors': errors})


@admin_bp.route('/admin/bulk-delete-jobs', methods=['POST'])
@login_required
@admin_required
def bulk_delete_jobs():
    """Массовое удаление заданий (до 50 за раз)."""
    data = request.get_json(silent=True) or {}
    job_ids = data.get('job_ids', [])

    if not isinstance(job_ids, list) or len(job_ids) == 0:
        return jsonify({'deleted': 0, 'failed': 0, 'errors': ['No job_ids provided']}), 400
    if len(job_ids) > 50:
        return jsonify({'deleted': 0, 'failed': len(job_ids), 'errors': ['Max 50 jobs per request']}), 400

    deleted = 0
    failed = 0
    errors = []

    for job_id in job_ids:
        rpc_result = postgrest_rpc('delete_job_cascade', {'p_job_id': job_id}, use_admin=True)
        if not rpc_result.ok:
            current_app.logger.error(
                "Bulk delete job RPC: failed for %s: status=%s text=%s",
                job_id, rpc_result.status_code, (rpc_result.text or '')[:200]
            )
        result_data = rpc_result.json() if rpc_result.ok else {}
        if not result_data.get('success'):
            failed += 1
            errors.append(f'RPC failed for {job_id}')
        else:
            deleted += 1

    return jsonify({'deleted': deleted, 'failed': failed, 'errors': errors})


# ── Справочники: навыки и вероисповедания ──────────────

@admin_bp.route('/admin/skills', methods=['GET'])
@login_required
@admin_required
def get_skills():
    # Пробуем сортировку по sort_order; если колонки нет — fallback на name
    resp = postgrest_admin_request('GET', 'skills?select=*&order=sort_order.asc,name.asc')
    if not resp.ok:
        resp = postgrest_admin_request('GET', 'skills?select=*&order=name.asc')
    return jsonify({'success': True, 'skills': resp.json() if resp.ok else []})

@admin_bp.route('/admin/skills', methods=['POST'])
@login_required
@admin_required
def add_skill():
    try:
        name = request.form.get('name', '').strip()
        if not name:
            flash('Название навыка не может быть пустым', 'danger')
            return redirect(url_for('admin.admin_panel', tab='dictionaries'))
        # Находим максимальный sort_order (если колонка есть) и добавляем +1
        max_order = 0
        existing = postgrest_admin_request('GET', 'skills?select=sort_order&order=sort_order.desc&limit=1')
        if not existing.ok:
            existing = postgrest_admin_request('GET', 'skills?select=id&order=name.desc&limit=1')
        if existing.ok and existing.json():
            item = existing.json()[0] if existing.json() else {}
            max_order = item.get('sort_order', 0)
        print('DIAG add_skill: before POST', flush=True)
        resp = postgrest_admin_request('POST', 'skills', json={'name': name, 'sort_order': max_order + 1})

        # ===== ДИАГНОСТИКА =====
        print(f'DIAG add_skill: POST skills status={resp.status_code}, ok={resp.ok}, text="{resp.text[:200]}"', flush=True)
        # =======================

        if resp.ok:
            flash(f'Навык «{name}» добавлен', 'success')
        else:
            current_app.logger.error(
                'add_skill: PostgREST error (status %s): %s',
                resp.status_code, resp.text
            )
            flash(f'Ошибка при добавлении навыка: {resp.text}', 'danger')
    except Exception as e:
        print(f'DIAG add_skill EXCEPTION: {e}', flush=True)
        current_app.logger.exception('add_skill: unexpected error')
        flash(f'Ошибка: {str(e)}', 'danger')
    return redirect(url_for('admin.admin_panel', tab='dictionaries'))

@admin_bp.route('/admin/skills/reorder', methods=['POST'])
@login_required
@admin_required
def reorder_skills():
    """Принять новый порядок навыков: массив [{id, sort_order}, ...]"""
    data = request.get_json() or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'error': 'items required'}), 400
    for item in items:
        resp = postgrest_admin_request('PATCH', f'skills?id=eq.{item["id"]}', json={'sort_order': item['sort_order']})
        assert_postgrest_ok(resp, f'пересортировка навыка {item["id"]}')
    return jsonify({'success': True})

@admin_bp.route('/admin/skills/<skill_id>', methods=['PUT'])
@login_required
@admin_required
def update_skill(skill_id):
    try:
        data = request.get_json(silent=True) or {}
        if not data.get('name'):
            data['name'] = request.form.get('name', request.form.get('skill_name', '')).strip()
        name = (data.get('name', '')).strip()
        if not name:
            return jsonify({'success': False, 'error': 'Name required'}), 400
        resp = postgrest_admin_request('PATCH', f'skills?id=eq.{skill_id}', json={'name': name})
        if not resp.ok:
            current_app.logger.error(
                'update_skill(id=%s): PostgREST error (status %s): %s',
                skill_id, resp.status_code, resp.text
            )
            return jsonify({'success': False, 'error': f'PostgREST error: {resp.text}'}), resp.status_code or 400
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception('update_skill(id=%s): unexpected error', skill_id)
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/admin/skills/<skill_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_skill(skill_id):
    resp1 = postgrest_admin_request('DELETE', f'user_skills?skill_id=eq.{skill_id}')
    resp2 = postgrest_admin_request('DELETE', f'job_skills?skill_id=eq.{skill_id}')
    if not resp1.ok:
        return jsonify({'success': False, 'error': 'Failed to cleanup user_skills'}), 500
    if not resp2.ok:
        return jsonify({'success': False, 'error': 'Failed to cleanup job_skills'}), 500
    resp = postgrest_admin_request('DELETE', f'skills?id=eq.{skill_id}')
    return jsonify({'success': resp.ok})

@admin_bp.route('/admin/bulk-delete-skills', methods=['POST'])
@login_required
@admin_required
def bulk_delete_skills():
    """Массовое удаление навыков (до 50 за раз).

    Использует оператор in.() PostgREST для выполнения трёх запросов
    вместо N*3 — удаление всех user_skills, job_skills и skills за раз.
    Возвращает сводку: deleted (сколько навыков удалено из skills),
    failed (сколько запросов к дочерним таблицам не удались).
    """
    data = request.get_json(silent=True) or {}
    skill_ids = data.get('skill_ids', [])

    if not isinstance(skill_ids, list) or len(skill_ids) == 0:
        return jsonify({'deleted': 0, 'failed': 0, 'errors': ['No skill_ids provided']}), 400
    if len(skill_ids) > 50:
        return jsonify({'deleted': 0, 'failed': len(skill_ids), 'errors': ['Max 50 skills per request']}), 400

    ids_filter = f'id=in.({",".join(str(sid) for sid in skill_ids)})'
    skill_id_filter = f'skill_id=in.({",".join(str(sid) for sid in skill_ids)})'

    errors = []
    failed = 0

    # 1. Каскадное удаление дочерних записей
    resp_user = postgrest_admin_request('DELETE', f'user_skills?{skill_id_filter}')
    if not resp_user.ok:
        errors.append(f'user_skills cleanup failed: {resp_user.text}')
        failed += 1

    resp_job = postgrest_admin_request('DELETE', f'job_skills?{skill_id_filter}')
    if not resp_job.ok:
        errors.append(f'job_skills cleanup failed: {resp_job.text}')
        failed += 1

    # 2. Удаление самих навыков
    resp = postgrest_admin_request('DELETE', f'skills?{ids_filter}')

    if not resp.ok:
        return jsonify({
            'deleted': 0,
            'failed': len(skill_ids),
            'errors': errors + [f'skills DELETE failed: {resp.text}']
        }), 500

    # Подсчёт удалённых: PostgREST возвращает массив удалённых строк
    deleted = len(resp.json()) if isinstance(resp.json(), list) else 0
    missing = len(skill_ids) - deleted
    if missing > 0:
        errors.append(f'{missing} skill(s) not found in database')

    return jsonify({'deleted': deleted, 'failed': failed, 'errors': errors})

@admin_bp.route('/admin/religions', methods=['GET'])
@login_required
@admin_required
def get_religions():
    resp = postgrest_admin_request('GET', 'religions?select=*&order=sort_order.asc,name.asc')
    if not resp.ok:
        resp = postgrest_admin_request('GET', 'religions?select=*&order=name.asc')
    return jsonify({'success': True, 'religions': resp.json() if resp.ok else []})

@admin_bp.route('/admin/religions', methods=['POST'])
@login_required
@admin_required
def add_religion():
    try:
        name = request.form.get('name', '').strip()
        if not name:
            flash('Название вероисповедания не может быть пустым', 'danger')
            return redirect(url_for('admin.admin_panel', tab='dictionaries'))
        max_order = 0
        existing = postgrest_admin_request('GET', 'religions?select=sort_order&order=sort_order.desc&limit=1')
        if not existing.ok:
            if is_circuit_open(existing):
                flash('Сервис временно недоступен. Попробуйте позже.', 'danger')
                current_app.logger.warning('add_religion: circuit breaker open, skipping GET fallback')
                return redirect(url_for('admin.admin_panel', tab='dictionaries'))
            # Fallback: если не удалось получить sort_order — используем 0
            current_app.logger.warning(
                'add_religion: GET max_order failed (status %s), using default 0',
                existing.status_code
            )
        elif existing.json():
            item = existing.json()[0] if existing.json() else {}
            max_order = item.get('sort_order', 0)

        print('DIAG add_religion: before POST', flush=True)
        resp = postgrest_admin_request('POST', 'religions', json={'name': name, 'sort_order': max_order + 1})

        # ===== ДИАГНОСТИКА =====
        print(f'DIAG add_religion: POST religions status={resp.status_code}, ok={resp.ok}, text="{resp.text[:200]}"', flush=True)
        # =======================

        if resp.ok:
            flash(f'Вероисповедание «{name}» добавлено', 'success')
        elif is_circuit_open(resp):
            flash('Сервис временно недоступен. Попробуйте позже.', 'danger')
            current_app.logger.warning('add_religion: circuit breaker open, POST not executed')
        elif resp.status_code == 0:
            # Таймаут / сетевой ошибка — status_code=0 означает, что запрос не дошёл
            flash('Сервер PostgREST не отвечает. Попробуйте позже.', 'danger')
            current_app.logger.error(
                'add_religion: PostgREST timeout/network error (status 0): %s',
                resp.text
            )
        else:
            current_app.logger.error(
                'add_religion: PostgREST error (status %s): %s',
                resp.status_code, resp.text
            )
            flash(f'Ошибка при добавлении вероисповедания: {resp.text}', 'danger')
    except Exception as e:
        print(f'DIAG add_religion EXCEPTION: {e}', flush=True)
        current_app.logger.exception('add_religion: unexpected error')
        flash(f'Ошибка: {str(e)}', 'danger')
    return redirect(url_for('admin.admin_panel', tab='dictionaries'))

@admin_bp.route('/admin/religions/reorder', methods=['POST'])
@login_required
@admin_required
def reorder_religions():
    """Принять новый порядок вероисповеданий: массив [{id, sort_order}, ...]"""
    data = request.get_json() or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'error': 'items required'}), 400
    for item in items:
        resp = postgrest_admin_request('PATCH', f'religions?id=eq.{item["id"]}', json={'sort_order': item['sort_order']})
        assert_postgrest_ok(resp, f'пересортировка вероисповедания {item["id"]}')
    return jsonify({'success': True})

@admin_bp.route('/admin/religions/<religion_id>', methods=['PUT'])
@login_required
@admin_required
def update_religion(religion_id):
    try:
        data = request.get_json(silent=True) or {}
        if not data.get('name'):
            data['name'] = request.form.get('name', request.form.get('religion_name', '')).strip()
        name = (data.get('name', '')).strip()
        if not name:
            return jsonify({'success': False, 'error': 'Name required'}), 400
        resp = postgrest_admin_request('PATCH', f'religions?id=eq.{religion_id}', json={'name': name})
        if not resp.ok:
            current_app.logger.error(
                'update_religion(id=%s): PostgREST error (status %s): %s',
                religion_id, resp.status_code, resp.text
            )
            return jsonify({'success': False, 'error': f'PostgREST error: {resp.text}'}), resp.status_code or 400
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception('update_religion(id=%s): unexpected error', religion_id)
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/admin/religions/<religion_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_religion(religion_id):
    resp = postgrest_admin_request('DELETE', f'religions?id=eq.{religion_id}')
    return jsonify({'success': resp.ok})

@admin_bp.route('/admin/bulk-delete-religions', methods=['POST'])
@login_required
@admin_required
def bulk_delete_religions():
    """Массовое удаление вероисповеданий (до 50 за раз).

    Использует оператор in.() PostgREST для одного запроса вместо N.
    Возвращает сводку: deleted (сколько записей удалено),
    failed и errors при ошибках.
    """
    data = request.get_json(silent=True) or {}
    religion_ids = data.get('religion_ids', [])

    if not isinstance(religion_ids, list) or len(religion_ids) == 0:
        return jsonify({'deleted': 0, 'failed': 0, 'errors': ['No religion_ids provided']}), 400
    if len(religion_ids) > 50:
        return jsonify({'deleted': 0, 'failed': len(religion_ids), 'errors': ['Max 50 religions per request']}), 400

    ids_filter = f'id=in.({",".join(str(rid) for rid in religion_ids)})'
    resp = postgrest_admin_request('DELETE', f'religions?{ids_filter}')

    if not resp.ok:
        return jsonify({
            'deleted': 0,
            'failed': len(religion_ids),
            'errors': [f'religions DELETE failed: {resp.text}']
        }), 500

    deleted = len(resp.json()) if isinstance(resp.json(), list) else 0
    errors = []
    missing = len(religion_ids) - deleted
    if missing > 0:
        errors.append(f'{missing} religion(s) not found in database')

    return jsonify({'deleted': deleted, 'failed': 0, 'errors': errors})

# ── Верификация работодателей ──────────────────────────

@admin_bp.route('/admin/approve/<user_id>', methods=['POST'])
@login_required
@admin_required
def approve_employer(user_id):
    resp = postgrest_admin_request('PATCH', f'profiles?id=eq.{user_id}',
                     json={'verification_status': 'approved'})
    if resp and resp.ok:
        flash('Работодатель верифицирован', 'success')
    else:
        flash('Ошибка при верификации', 'danger')
    return redirect(url_for('admin.admin_panel', tab='verification'))


@admin_bp.route('/admin/reject/<user_id>', methods=['POST'])
@login_required
@admin_required
def reject_employer(user_id):
    resp = postgrest_admin_request('PATCH', f'profiles?id=eq.{user_id}',
                     json={'verification_status': 'rejected'})
    if resp and resp.ok:
        flash('Верификация отклонена', 'warning')
    else:
        flash('Ошибка при отклонении', 'danger')
    return redirect(url_for('admin.admin_panel', tab='verification'))


@admin_bp.route('/admin/verify-employer/<user_id>', methods=['POST'])
@login_required
@admin_required
def verify_employer(user_id):
    resp = postgrest_admin_request('PATCH', f'profiles?id=eq.{user_id}', json={'verification_status': 'approved'})
    if assert_postgrest_ok(resp, 'верификация работодателя'):
        flash('Работодатель верифицирован', 'success')
    return redirect(url_for('admin.admin_panel', tab='verification'))


@admin_bp.route('/api/admin/job-stats')
@login_required
@admin_required
def job_stats():
    """Статистика заданий для админ-дашборда.

    Использует RPC get_job_stats для серверной агрегации (O(1) вместо O(n)).
    При отсутствии RPC — fallback на загрузку всех записей с подсчётом в Python.
    """
    try:
        # Пробуем RPC с серверной агрегацией
        rpc_resp = postgrest_rpc('get_job_stats', {}, use_admin=True)
        if rpc_resp.ok and rpc_resp.json():
            data = rpc_resp.json()
            # RPC может вернуть dict или list[dict]
            if isinstance(data, dict):
                return jsonify({
                    "total_jobs": data.get('total', 0),
                    "open_jobs": data.get('open', 0),
                    "completed_jobs": data.get('completed', 0),
                    "cancelled_jobs": data.get('cancelled', 0),
                })
            elif isinstance(data, list) and data:
                stats = data[0]
                return jsonify({
                    "total_jobs": stats.get('total', 0),
                    "open_jobs": stats.get('open', 0),
                    "completed_jobs": stats.get('completed', 0),
                    "cancelled_jobs": stats.get('cancelled', 0),
                })

        # Fallback: загружаем все статусы и считаем в Python (работает без RPC)
        resp = postgrest_admin_request('GET', 'jobs?select=status')
        if resp.ok and resp.json():
            statuses = [j.get('status', '') for j in resp.json()]
            return jsonify({
                "total_jobs": len(statuses),
                "open_jobs": statuses.count('open'),
                "completed_jobs": statuses.count('completed'),
                "cancelled_jobs": statuses.count('cancelled'),
            })
        return jsonify({"total_jobs": 0, "open_jobs": 0, "completed_jobs": 0, "cancelled_jobs": 0, "error": True})
    except Exception:
        return jsonify({"total_jobs": 0, "open_jobs": 0, "completed_jobs": 0, "cancelled_jobs": 0, "error": True})


# ═══════════════════════════════════════════════════════════
# Diagnostic endpoint: show applied migrations
# Protected by SECRET_KEY (X-Admin-Token header)
# ═══════════════════════════════════════════════════════════

@admin_bp.route('/api/fix-permissions', methods=['POST'])
def fix_permissions():
    """Fix PostgreSQL permissions: GRANT ALL to app role (trudnikapp) and grant PostgREST roles."""
    import logging
    log = logging.getLogger(__name__)

    token = request.headers.get('X-Admin-Token', '')
    if not token or token != current_app.config.get('SECRET_KEY', ''):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    # Get database URL directly from env vars (avoid @property issue)
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('PGDATABASE_URL', '')
    if not db_url:
        # Try to construct from PG* vars
        pg_user = os.environ.get('PGUSER', '')
        pg_password = os.environ.get('PGPASSWORD', '')
        pg_host = os.environ.get('PGHOST', '')
        pg_port = os.environ.get('PGPORT', '5432')
        pg_database = os.environ.get('PGDATABASE', '')
        if all([pg_user, pg_password, pg_host, pg_database]):
            db_url = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
        else:
            return jsonify({'success': False, 'error': 'DATABASE_URL not configured'}), 500

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()

        grants = [
            # Role grants — критично для PostgREST: даём trudnikapp права
            # переключаться на роли service_role и anon (SET ROLE)
            "GRANT service_role TO trudnikapp",
            "GRANT anon TO trudnikapp",
            "GRANT authenticated TO trudnikapp",
            "ALTER ROLE trudnikapp INHERIT",
            # Object privileges
            "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trudnikapp",
            "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trudnikapp",
            "GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO trudnikapp",
            "GRANT USAGE ON SCHEMA public TO trudnikapp",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO trudnikapp",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO trudnikapp",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO trudnikapp",
            "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO anon",
            "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO anon",
            "GRANT USAGE ON SCHEMA public TO anon",
        ]

        results = []
        errors = []
        for sql in grants:
            try:
                cur.execute(sql)
                results.append(f"OK: {sql[:60]}...")
            except Exception as e:
                errors.append(f"FAIL: {sql[:60]}... -> {e}")

        cur.close()
        conn.close()

        log.info("fix-permissions: %d OK, %d errors", len(results), len(errors))
        return jsonify({
            'success': len(errors) == 0,
            'executed': len(results),
            'failed': len(errors),
            'results': results,
            'errors': errors,
        })
    except ImportError:
        return jsonify({'success': False, 'error': 'psycopg2 not installed'}), 500
    except Exception as e:
        log.error("fix-permissions: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/migrations-status', methods=['GET'])
def migrations_status():
    """Return the list of applied migrations from _migrations tracking table."""
    import logging
    log = logging.getLogger(__name__)

    token = request.headers.get('X-Admin-Token', '')
    if not token or token != current_app.config.get('SECRET_KEY', ''):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    resp = postgrest_admin_request('GET', '_migrations?select=*&order=applied_at.asc')
    if resp.ok:
        migrations = resp.json() if isinstance(resp.json(), list) else []
        return jsonify({
            'success': True,
            'count': len(migrations),
            'migrations': migrations,
        })
    else:
        log.warning("migrations-status: query failed: %s", resp.status_code)
        return jsonify({
            'success': False,
            'count': 0,
            'migrations': [],
            'error': f'PostgREST query failed: {resp.status_code}',
        })


# ═══════════════════════════════════════════════════════════
# Emergency endpoint: reset all users and create test accounts
# Protected by SECRET_KEY (X-Admin-Token header)
# ═══════════════════════════════════════════════════════════

@admin_bp.route('/api/reset-users', methods=['POST'])
def reset_users():
    """
    Delete all users and create three test accounts.
    Uses DIRECT SQL connection (psycopg2) to bypass PostgREST permission issues.

    Creates:
    - admin@test.ru (admin)
    - org@test.ru (employer)
    - trud@test.ru (worker)
    All with password Step@1986.

    Protected by X-Admin-Token header (must match SECRET_KEY).
    """
    import logging
    log = logging.getLogger(__name__)

    token = request.headers.get('X-Admin-Token', '')
    expected_token = current_app.config.get('SECRET_KEY', '')
    if not token or token != expected_token:
        log.warning("reset-users: invalid or missing X-Admin-Token")
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    result = {
        'success': True,
        'deleted': 0,
        'delete_failed': 0,
        'created': [],
        'create_failed': [],
        'errors': [],
    }

    # --- Get database connection ---
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('PGDATABASE_URL', '')
    if not db_url:
        pg_user = os.environ.get('PGUSER', '')
        pg_password = os.environ.get('PGPASSWORD', '')
        pg_host = os.environ.get('PGHOST', '')
        pg_port = os.environ.get('PGPORT', '5432')
        pg_database = os.environ.get('PGDATABASE', '')
        if all([pg_user, pg_password, pg_host, pg_database]):
            db_url = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
        else:
            return jsonify({'success': False, 'error': 'DATABASE_URL not configured'}), 500

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()

        # --- Step 1: Get all user IDs ---
        log.info("reset-users: fetching all users...")
        cur.execute("SELECT id, email, role FROM profiles ORDER BY created_at")
        all_users = cur.fetchall()
        log.info("reset-users: found %d users", len(all_users))

        # --- Step 2: Delete all users directly via SQL ---
        for uid, email, role in all_users:
            log.info("reset-users: deleting %s (%s)...", email, uid)
            try:
                # Delete related records first (same order as delete_user_cascade)
                if role == 'employer':
                    # Delete jobs created by this employer
                    cur.execute("DELETE FROM jobs WHERE employer_id = %s", [uid])
                cur.execute("DELETE FROM applications WHERE worker_id = %s", [uid])
                cur.execute("DELETE FROM notifications WHERE user_id = %s", [uid])
                cur.execute("DELETE FROM favorites WHERE user_id = %s OR target_id = %s", [uid, uid])
                cur.execute("DELETE FROM job_favorites WHERE user_id = %s", [uid])
                cur.execute("DELETE FROM blacklists WHERE user_id = %s OR blocked_user_id = %s", [uid, uid])
                cur.execute("DELETE FROM ratings WHERE rater_user_id = %s OR rated_user_id = %s", [uid, uid])
                cur.execute("DELETE FROM invitations WHERE employer_id = %s OR worker_id = %s", [uid, uid])
                cur.execute("DELETE FROM user_skills WHERE user_id = %s", [uid])
                cur.execute("DELETE FROM push_subscriptions WHERE user_id = %s", [uid])
                cur.execute("DELETE FROM messages WHERE sender_id = %s", [uid])
                # Finally delete the profile
                cur.execute("DELETE FROM profiles WHERE id = %s", [uid])
                result['deleted'] += 1
                log.info("reset-users: deleted %s ok", email)
            except Exception as e:
                result['delete_failed'] += 1
                result['errors'].append(f"Failed to delete {email}: {e}")
                log.error("reset-users: failed to delete %s: %s", email, e)

        log.info("reset-users: deleted=%d, failed=%d", result['deleted'], result['delete_failed'])

        # --- Step 3: Create three test users via SQL (using pgcrypto crypt()) ---
        test_users = [
            ('admin@test.ru', 'Step@1986', 'Администратор', 'admin'),
            ('org@test.ru',   'Step@1986', 'Организатор',   'employer'),
            ('trud@test.ru',  'Step@1986', 'Трудник Тест',  'worker'),
        ]

        for email, password, full_name, role in test_users:
            log.info("reset-users: creating %s (%s)...", email, role)
            try:
                cur.execute("""
                    INSERT INTO profiles (id, email, password_hash, full_name, role)
                    VALUES (gen_random_uuid(), %s, crypt(%s, gen_salt('bf')), %s, %s)
                    RETURNING id
                """, (email, password, full_name, role))
                new_id = cur.fetchone()[0]
                result['created'].append({'email': email, 'role': role, 'id': str(new_id)})
                log.info("reset-users: created %s with id=%s", email, new_id)
            except Exception as e:
                result['create_failed'].append(email)
                result['errors'].append(f"Failed to create {email}: {e}")
                log.error("reset-users: failed to create %s: %s", email, e)

        log.info("reset-users: created=%d, failed=%d",
                 len(result['created']), len(result['create_failed']))

        # --- Step 4: Final verification ---
        cur.execute("SELECT email, role FROM profiles ORDER BY role, email")
        final_users = [{'email': row[0], 'role': row[1]} for row in cur.fetchall()]
        result['final_count'] = len(final_users)
        result['final_users'] = final_users
        log.info("reset-users: final user count=%d", len(final_users))

        cur.close()
        conn.close()

    except ImportError:
        return jsonify({'success': False, 'error': 'psycopg2 not installed'}), 500
    except Exception as e:
        log.error("reset-users: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500

    if result['delete_failed'] > 0 or len(result['create_failed']) > 0:
        result['success'] = False

    return jsonify(result)


@admin_bp.route('/api/reset-circuit-breaker', methods=['POST'])
def reset_circuit_breaker():
    """
    Сбросить Circuit Breaker PostgREST-клиента в состояние CLOSED.
    Полезно после исправления ошибок, чтобы не ждать таймаута.

    Protected by X-Admin-Token header (must match SECRET_KEY).
    """
    import logging
    log = logging.getLogger(__name__)

    token = request.headers.get('X-Admin-Token', '')
    expected_token = current_app.config.get('SECRET_KEY', '')
    if not token or token != expected_token:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        from app.utils.postgrest_client import _cb_postgrest, _cb_admin, get_circuit_breaker_state

        _cb_postgrest.reset()
        _cb_admin.reset()

        state = get_circuit_breaker_state()
        log.info("Circuit Breaker reset: %s", state)

        return jsonify({
            'success': True,
            'message': 'Circuit Breaker сброшен в CLOSED',
            'state': state,
        })
    except Exception as e:
        log.error("reset-circuit-breaker: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500
