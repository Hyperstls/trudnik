"""Админ-панель: диагностика, circuit breaker, статистика заданий.

Выделен из app/blueprints/admin.py (задача 4-5).
"""

import hmac as _hmac
import logging
import os

from flask import Blueprint, current_app, jsonify, request

from app.decorators import login_required, admin_required
from app.utils import postgrest_admin_request, postgrest_rpc

log = logging.getLogger(__name__)

admin_diagnostics_bp = Blueprint('admin_diagnostics', __name__, url_prefix='/admin')


@admin_diagnostics_bp.route('/api/admin/job-stats')
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


@admin_diagnostics_bp.route('/api/migrations-status', methods=['GET'])
def migrations_status():
    """Return the list of applied migrations from _migrations tracking table."""
    token = request.headers.get('X-Admin-Token', '')
    expected = current_app.config.get('ADMIN_API_TOKEN', '')
    if not expected or not _hmac.compare_digest(token, expected):
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


@admin_diagnostics_bp.route('/api/reset-circuit-breaker', methods=['POST'])
def reset_circuit_breaker():
    """
    Сбросить Circuit Breaker PostgREST-клиента в состояние CLOSED.
    Полезно после исправления ошибок, чтобы не ждать таймаута.

    Protected by X-Admin-Token header (must match SECRET_KEY).
    """
    token = request.headers.get('X-Admin-Token', '')
    expected_token = current_app.config.get('ADMIN_API_TOKEN', '')
    allowed_ips = [ip.strip() for ip in os.environ.get('ADMIN_API_ALLOWED_IPS', '').split(',') if ip.strip()]
    if allowed_ips and request.remote_addr not in allowed_ips:
        current_app.logger.warning('Emergency endpoint access from forbidden IP: %s', request.remote_addr)
        return jsonify({'error': 'Forbidden'}), 403
    if not expected_token or not _hmac.compare_digest(token, expected_token):
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