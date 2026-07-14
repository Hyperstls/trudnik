"""Админ-панель: управление пользователями.

Выделен из app/blueprints/admin.py (задача 4-5).
"""

from flask import Blueprint, current_app, flash, jsonify, redirect, request, session, url_for

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