"""Админ-панель: управление пользователями.

Выделен из app/blueprints/admin.py (задача 4-5).
"""

from flask import (Blueprint, current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)

from app.decorators import login_required, admin_required, validate_uuid
from app.utils import postgrest_admin_request, postgrest_rpc
from app.utils.helpers import assert_postgrest_ok
from app.services.admin_service import log_admin_action

admin_users_bp = Blueprint('admin_users', __name__, url_prefix='/admin')


@admin_users_bp.route('/users/<user_id>/role', methods=['POST'])
@login_required
@admin_required
@validate_uuid('user_id')
def update_user_role(user_id):
    if user_id == session.get('user_id'):
        flash('Нельзя изменить свою роль', 'danger')
        return redirect(url_for('admin_dashboard.admin_panel', tab='users'))

    target_resp = postgrest_admin_request('GET', f'profiles?id=eq.{user_id}&select=role')
    if target_resp.ok and target_resp.json():
        target_role = target_resp.json()[0].get('role', '')
        if target_role == 'admin':
            flash('Нельзя изменить роль другого администратора', 'danger')
            return redirect(url_for('admin_dashboard.admin_panel', tab='users'))

    new_role = request.form.get('role', '')
    if new_role in ('worker', 'employer', 'admin'):
        resp = postgrest_admin_request('PATCH', f'profiles?id=eq.{user_id}', json={'role': new_role})
        if assert_postgrest_ok(resp, 'смена роли пользователя'):
            flash(f'Роль изменена на {new_role}', 'success')
            log_admin_action('update_role', table_name='profiles', record_id=user_id,
                             new_data={'role': new_role})
    else:
        flash('Недопустимая роль', 'danger')
    return redirect(url_for('admin_dashboard.admin_panel', tab='users'))


@admin_users_bp.route('/users/<user_id>/delete', methods=['POST'])
@login_required
@admin_required
@validate_uuid('user_id')
def delete_user(user_id):
    # Проверяем что target не является admin
    target_resp = postgrest_admin_request('GET', f'profiles?id=eq.{user_id}&select=role')
    if target_resp.ok and target_resp.json():
        target_data = target_resp.json()
        if isinstance(target_data, list) and target_data:
            target_role = target_data[0].get('role', '')
            if target_role == 'admin':
                flash('Нельзя удалить администратора', 'danger')
                return redirect(url_for('admin_dashboard.admin_panel', tab='users'))
    
    rpc_result = postgrest_rpc('delete_user_cascade', {'p_user_id': user_id}, use_admin=True)
    if not rpc_result.ok:
        current_app.logger.error(
            "Admin delete user RPC: failed for %s: status=%s text=%s",
            user_id, rpc_result.status_code, (rpc_result.text or '')[:200]
        )
    result_data = rpc_result.json() if rpc_result.ok else {}
    if not result_data.get('success'):
        flash('Ошибка при удалении пользователя', 'danger')
        return redirect(url_for('admin_dashboard.admin_panel', tab='users'))

    # Профиль удалён — B5-проверка существования в login_required надёжно блокирует JWT
    log_admin_action('delete_user', table_name='profiles', record_id=user_id)
    flash('Пользователь удалён', 'success')
    return redirect(url_for('admin_dashboard.admin_panel', tab='users'))


@admin_users_bp.route('/users/<user_id>/unsuspend', methods=['POST'])
@login_required
@admin_required
@validate_uuid('user_id')
def unsuspend_user(user_id):
    """Phase 3: ручная разморозка пользователя администратором."""
    rpc = postgrest_rpc('unsuspend_user', {'p_user_id': user_id}, use_admin=True)
    ok = rpc.ok and (rpc.json() if rpc.ok else {}).get('ok', True) is not False
    if rpc.ok:
        log_admin_action('unsuspend_user', table_name='profiles', record_id=user_id)
        flash('Пользователь разморожен', 'success')
    else:
        current_app.logger.error('Admin unsuspend RPC failed for %s: %s', user_id, (rpc.text or '')[:200])
        flash('Не удалось разморозить пользователя', 'danger')
    return redirect(url_for('admin_dashboard.admin_panel', tab='users'))


@admin_users_bp.route('/complaints')
@login_required
@admin_required
def complaints_queue():
    """Phase 3: очередь жалоб для ручной модерации администратором."""
    status_filter = request.args.get('status', 'new')
    q = ('user_reports?order=created_at.desc'
         '&select=id,reason,created_at,status,reporter_id,reported_id&limit=100')
    if status_filter != 'all':
        q += f'&status=eq.{status_filter}'
    resp = postgrest_admin_request('GET', q)
    reports = resp.json() if resp.ok else []

    ids = set()
    for r in reports:
        if r.get('reporter_id'):
            ids.add(r['reporter_id'])
        if r.get('reported_id'):
            ids.add(r['reported_id'])
    names = {}
    if ids:
        ids_str = ','.join(sorted(ids))
        pr = postgrest_admin_request(
            'GET', f'profiles?id=in.({ids_str})&select=id,full_name,role,rating'
        )
        for p in (pr.json() if pr.ok else []):
            names[p['id']] = p

    counts_resp = postgrest_admin_request('GET', 'user_reports?select=reported_id')
    counts = {}
    for r in (counts_resp.json() if counts_resp.ok else []):
        counts[r['reported_id']] = counts.get(r['reported_id'], 0) + 1

    return render_template('admin_complaints.html', reports=reports, names=names,
                           counts=counts, status_filter=status_filter)


@admin_users_bp.route('/complaints/<report_id>/review', methods=['POST'])
@login_required
@admin_required
@validate_uuid('report_id')
def review_complaint(report_id):
    """Рассмотреть жалобу: block (заморозить) или dismiss (отклонить)."""
    action = request.form.get('action', '')
    if action not in ('block', 'dismiss'):
        flash('Неизвестное действие', 'danger')
        return redirect(url_for('admin_users.complaints_queue'))
    admin_id = session.get('user_id')
    rpc = postgrest_rpc('review_complaint',
                        {'p_report_id': report_id, 'p_action': action, 'p_admin_id': admin_id},
                        use_admin=True)
    data = rpc.json() if rpc.ok else {}
    if data.get('ok'):
        log_admin_action(f'review_complaint_{action}', table_name='user_reports', record_id=report_id)
        flash('Пользователь заблокирован по жалобе' if action == 'block' else 'Жалоба отклонена', 'success')
    else:
        flash('Не удалось обработать жалобу', 'danger')
    return redirect(url_for('admin_users.complaints_queue'))


@admin_users_bp.route('/bulk-delete-users', methods=['POST'])
@login_required
@admin_required
def bulk_delete_users():
    data = request.get_json(silent=True) or {}
    user_ids = data.get('user_ids', [])

    if not isinstance(user_ids, list) or len(user_ids) == 0:
        return jsonify({'deleted': 0, 'failed': 0, 'errors': ['No user_ids provided']}), 400
    if len(user_ids) > 20:
        return jsonify({'deleted': 0, 'failed': len(user_ids), 'errors': ['Max 20 users per request']}), 400

    # P0: Check that we are not trying to delete other admins
    user_ids_str = ','.join(user_ids)
    profiles_resp = postgrest_admin_request('GET', f'profiles?id=in.({user_ids_str})&select=id,role')
    if profiles_resp.ok and profiles_resp.json():
        for p in profiles_resp.json():
            if p.get('role') == 'admin' and str(p['id']) != str(session.get('user_id', '')):
                return jsonify({
                    'deleted': 0, 'failed': len(user_ids),
                    'errors': ['Cannot delete another admin (user_id=%s)' % p['id']]
                }), 403

    deleted = 0
    failed = 0
    errors = []

    for user_id in user_ids:
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
        deleted += 1

    return jsonify({'deleted': deleted, 'failed': failed, 'errors': errors})


# ============================================================
# Инструменты тестирования: создание тестового пользователя (pre-verified)
# и подтверждение email вручную (для несуществующих доменов, напр. test.ru)
# ============================================================
@admin_users_bp.route('/test-user', methods=['GET', 'POST'])
@login_required
@admin_required
def test_user_tools():
    """Создание тестового пользователя с подтверждённым email (без реальной почты)
    либо ручное подтверждение email существующего пользователя."""
    if request.method == 'POST':
        action = request.form.get('action', '')
        email = (request.form.get('email') or '').strip().lower()

        if action == 'create':
            password = request.form.get('password', '')
            full_name = (request.form.get('full_name') or '').strip() or 'Тестовый пользователь'
            role = request.form.get('role', 'worker')
            if role not in ('worker', 'employer'):
                role = 'worker'
            if not email or len(password) < 8:
                flash('Укажите email и пароль (мин. 8 символов)', 'danger')
                return redirect(url_for('admin_users.test_user_tools'))
            resp = postgrest_rpc('register_user', {
                'p_email': email, 'p_password': password,
                'p_full_name': full_name, 'p_role': role,
            }, use_admin=True)
            if resp.ok:
                postgrest_admin_request('PATCH', f'profiles?email=eq.{email}',
                                        json={'email_verified': True})
                log_admin_action('create_test_user', table_name='profiles', record_id=email, new_data={'role': role})
                flash(f'Тестовый пользователь {email} создан, email подтверждён. Можно войти.', 'success')
            else:
                err = ''
                try:
                    err = (resp.json() or {}).get('message', '') or resp.text
                except Exception:
                    err = resp.text
                flash(f'Ошибка создания: {(err or "")[:200]}', 'danger')
            return redirect(url_for('admin_users.test_user_tools'))

        if action == 'verify':
            if not email:
                flash('Укажите email', 'danger')
                return redirect(url_for('admin_users.test_user_tools'))
            resp = postgrest_admin_request('PATCH', f'profiles?email=eq.{email}',
                                           json={'email_verified': True})
            if resp.ok:
                log_admin_action('manual_verify_email', table_name='profiles', record_id=email)
                flash(f'Email {email} подтверждён. Пользователь может войти.', 'success')
            else:
                flash('Не удалось подтвердить (пользователь не найден?)', 'danger')
            return redirect(url_for('admin_users.test_user_tools'))

        flash('Неизвестное действие', 'danger')
        return redirect(url_for('admin_users.test_user_tools'))

    return render_template('admin_test_user.html')


# ============================================================
# Редактор статичных страниц (Условия / Политика конфиденциальности)
# ============================================================
@admin_users_bp.route('/content/<slug>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_site_content(slug):
    """Редактирование текста /terms или /privacy (хранится в site_pages)."""
    if slug not in ('terms', 'privacy'):
        flash('Неизвестная страница', 'danger')
        return redirect('/admin')
    default_title = 'Условия использования' if slug == 'terms' else 'Политика конфиденциальности'

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip() or default_title
        content = request.form.get('content') or ''
        from datetime import datetime, timezone
        body = [{'slug': slug, 'title': title, 'content': content,
                 'updated_at': datetime.now(timezone.utc).isoformat()}]
        resp = postgrest_admin_request(
            'POST', 'site_pages', json=body,
            headers={'Prefer': 'resolution=merge-duplicates'})
        if resp.ok:
            log_admin_action('edit_site_page', table_name='site_pages', record_id=slug)
            flash('Страница сохранена', 'success')
        else:
            flash('Ошибка сохранения: ' + (resp.text or '')[:200], 'danger')
        return redirect(url_for('admin_users.edit_site_content', slug=slug))

    page = {'title': default_title, 'content': ''}
    resp = postgrest_admin_request('GET', f'site_pages?slug=eq.{slug}&select=title,content&limit=1')
    if resp.ok:
        data = resp.json()
        if data:
            page = data[0]
    return render_template('admin_edit_content.html', slug=slug,
                           page_title=page.get('title') or default_title,
                           content=page.get('content') or '')