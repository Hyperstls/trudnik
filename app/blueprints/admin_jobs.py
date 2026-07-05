"""Админ-панель: управление заданиями.

Выделен из app/blueprints/admin.py (задача 4-5).
"""

from flask import Blueprint, current_app, flash, jsonify, redirect, request, url_for

from app.decorators import login_required, admin_required
from app.utils import postgrest_admin_request, postgrest_rpc
from app.utils.helpers import assert_postgrest_ok
from app.services.admin_service import log_admin_action

admin_jobs_bp = Blueprint('admin_jobs', __name__, url_prefix='/admin')


@admin_jobs_bp.route('/jobs/<job_id>/status', methods=['POST'])
@login_required
@admin_required
def update_job_status(job_id):
    new_status = request.form.get('status', '')
    if new_status in ('open', 'completed', 'cancelled'):
        resp = postgrest_admin_request('PATCH', f'jobs?id=eq.{job_id}', json={'status': new_status})
        if assert_postgrest_ok(resp, 'изменение статуса задания'):
            flash(f'Статус задания изменён на {new_status}', 'success')
            log_admin_action('update_status', table_name='jobs', record_id=job_id,
                             new_data={'status': new_status})
    return redirect(url_for('admin_dashboard.admin_panel', tab='jobs'))


@admin_jobs_bp.route('/jobs/<job_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_job_admin(job_id):
    _delete_job_cascade(job_id)
    log_admin_action('delete_job', table_name='jobs', record_id=job_id)
    flash('Задание удалено', 'success')
    return redirect(url_for('admin_dashboard.admin_panel', tab='jobs'))


def _delete_job_cascade(job_id):
    """Каскадное удаление задания и всех связанных записей через RPC."""
    rpc_result = postgrest_rpc('delete_job_cascade', {'p_job_id': job_id}, use_admin=True)
    if not rpc_result.ok:
        current_app.logger.error(
            "Admin delete job RPC: failed for %s: status=%s text=%s",
            job_id, rpc_result.status_code, (rpc_result.text or '')[:200]
        )


@admin_jobs_bp.route('/bulk-delete-jobs', methods=['POST'])
@login_required
@admin_required
def bulk_delete_jobs():
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