"""Админ-панель: верификация пользователей.

Выделен из app/blueprints/admin.py (задача 4-5).
"""

from flask import Blueprint, flash, redirect, request, url_for

from app.decorators import login_required, admin_required, validate_uuid
from app.utils import postgrest_admin_request
from app.services.admin_service import log_admin_action

admin_verification_bp = Blueprint('admin_verification', __name__, url_prefix='/admin')


@admin_verification_bp.route('/approve/<user_id>', methods=['POST'])
@login_required
@admin_required
@validate_uuid('user_id')
def approve_employer(user_id):
    resp = postgrest_admin_request('PATCH', f'profiles?id=eq.{user_id}',
                     json={'verification_status': 'approved'})
    if resp and resp.ok:
        log_admin_action('verify_approve', table_name='profiles', record_id=user_id,
                         old_data=None, new_data={'verification_status': 'approved'})
        flash('Работодатель верифицирован', 'success')
    else:
        flash('Ошибка при верификации', 'danger')
    return redirect(url_for('admin_dashboard.admin_panel', tab='verification'))


@admin_verification_bp.route('/reject/<user_id>', methods=['POST'])
@login_required
@admin_required
@validate_uuid('user_id')
def reject_employer(user_id):
    resp = postgrest_admin_request('PATCH', f'profiles?id=eq.{user_id}',
                     json={'verification_status': 'rejected'})
    if resp and resp.ok:
        log_admin_action('verify_reject', table_name='profiles', record_id=user_id,
                         old_data=None, new_data={'verification_status': 'rejected'})
        flash('Верификация отклонена', 'warning')
    else:
        flash('Ошибка при отклонении', 'danger')
    return redirect(url_for('admin_dashboard.admin_panel', tab='verification'))