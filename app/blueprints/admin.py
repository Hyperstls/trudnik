from datetime import datetime
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for, jsonify

from app.decorators import login_required, role_required, admin_required, handle_errors
from app.utils import cache_for, sanitize_postgrest, postgrest_request, postgrest_admin_request, postgrest_rpc
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

    # Навыки — справочник (загружается через JS, но данные нужны для рендера)
    skills = []
    if tab == 'skills':
        skills_resp = postgrest_admin_request('GET', 'skills?select=*&order=sort_order.asc,name.asc')
        skills = skills_resp.json() if skills_resp.ok else []

    return render_template('admin.html',
                           tab=tab, stats=stats, users=users,
                           jobs=jobs, pending=pending, verified=verified,
                           skills=skills)


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

    # Amvera: удаление из auth.users не требуется (нет Supabase Auth)
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

        # Amvera: удаление из auth.users не требуется (нет Supabase Auth)
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
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    # Находим максимальный sort_order (если колонка есть) и добавляем +1
    max_order = 0
    existing = postgrest_admin_request('GET', 'skills?select=sort_order&order=sort_order.desc&limit=1')
    if not existing.ok:
        existing = postgrest_admin_request('GET', 'skills?select=id&order=name.desc&limit=1')
    if existing.ok and existing.json():
        item = existing.json()[0] if existing.json() else {}
        max_order = item.get('sort_order', 0)
    resp = postgrest_admin_request('POST', 'skills', json={'name': name, 'sort_order': max_order + 1})
    if resp.ok:
        return jsonify({'success': True, 'skill': resp.json()[0] if isinstance(resp.json(), list) else resp.json()})
    return jsonify({'success': False, 'error': resp.text}), 400

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
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    resp = postgrest_admin_request('PATCH', f'skills?id=eq.{skill_id}', json={'name': name})
    return jsonify({'success': resp.ok})

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
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    max_order = 0
    existing = postgrest_admin_request('GET', 'religions?select=sort_order&order=sort_order.desc&limit=1')
    if not existing.ok:
        existing = postgrest_admin_request('GET', 'religions?select=id&order=name.desc&limit=1')
    if existing.ok and existing.json():
        item = existing.json()[0] if existing.json() else {}
        max_order = item.get('sort_order', 0)
    resp = postgrest_admin_request('POST', 'religions', json={'name': name, 'sort_order': max_order + 1})
    if resp.ok:
        return jsonify({'success': True, 'religion': resp.json()[0] if isinstance(resp.json(), list) else resp.json()})
    return jsonify({'success': False, 'error': resp.text}), 400

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
    data = request.get_json() or {}
    name = (data.get('name', '')).strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    resp = postgrest_admin_request('PATCH', f'religions?id=eq.{religion_id}', json={'name': name})
    return jsonify({'success': resp.ok})

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
