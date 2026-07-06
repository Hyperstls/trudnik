"""Админ-дашборд: главная панель, статистика, health check.

Выделен из app/blueprints/admin.py (задача 4-5).
"""

from datetime import datetime, timezone
from pathlib import Path
import subprocess

from flask import Blueprint, current_app, jsonify, render_template, request, session

from app.decorators import login_required, admin_required
from app.utils import sanitize_postgrest, postgrest_admin_request
from app.services.admin_service import get_dashboard_stats

admin_dashboard_bp = Blueprint('admin_dashboard', __name__, url_prefix='/admin')


@admin_dashboard_bp.route('/api/health')
def health_check():
    """Health check endpoint для мониторинга."""
    return jsonify({'status': 'ok', 'timestamp': datetime.now(timezone.utc).isoformat()})


@admin_dashboard_bp.route('')
@login_required
@admin_required
def admin_panel():
    """Админ-панель: дашборд, пользователи, задания, верификация."""
    tab = request.args.get('tab', 'dashboard')

    # Дашборд: статистика через сервис
    stats = {}
    if tab == 'dashboard':
        stats = get_dashboard_stats()

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
        for j in jobs:
            emp = j.get('employer')
            if emp and isinstance(emp, list) and len(emp) > 0:
                j['employer_name'] = emp[0].get('full_name', '—')
            elif emp and isinstance(emp, dict):
                j['employer_name'] = emp.get('full_name', '—')
            else:
                j['employer_name'] = '—'

    # Верификация
    pending = []
    verified = []
    if tab == 'verification':
        resp = postgrest_admin_request(
            'GET',
            'profiles?verification_status=not.is.null&select=*&order=updated_at.desc&limit=50'
        )
        all_verify = resp.json() if resp.ok else []
        pending = [u for u in all_verify if u.get('verification_status') == 'pending']
        verified = [u for u in all_verify if u.get('verification_status') in ('approved', 'rejected')]

    # Справочники
    skills = []
    religions = []
    if tab == 'dictionaries' or tab == 'skills' or tab == 'religions':
        skills_resp = postgrest_admin_request('GET', 'skills?select=*&order=sort_order.asc,name.asc')
        skills = skills_resp.json() if skills_resp.ok else []
        religions_resp = postgrest_admin_request('GET', 'religions?select=*&order=sort_order.asc,name.asc')
        religions = religions_resp.json() if religions_resp.ok else []

    # Актуальная версия
    try:
        version_path = Path(current_app.root_path).parent / 'VERSION'
        if version_path.exists():
            actual_version = version_path.read_text(encoding='utf-8').strip()
        else:
            actual_version = subprocess.check_output(
                ['git', 'log', '-1', '--format=%h %s (%ai)'],
                cwd=str(Path(current_app.root_path).parent), text=True
            ).strip()
    except Exception as e:
        current_app.logger.warning('Failed to get version: %s', e, exc_info=True)
        actual_version = 'dev'

    return render_template('admin.html',
                           tab=tab, stats=stats, users=users,
                           jobs=jobs, pending=pending, verified=verified,
                           skills=skills, religions=religions,
                           actual_version=actual_version)