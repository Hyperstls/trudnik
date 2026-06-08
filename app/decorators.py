import secrets
from functools import wraps

from flask import abort, flash, redirect, request, session, url_for

from app.utils import supabase_request


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'access_token' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'access_token' not in session:
                return redirect(url_for('auth.login'))
            resp = supabase_request('GET', f'profiles?id=eq.{session["user_id"]}&select=role')
            data = resp.json()
            if not data or not isinstance(data, list) or not data:
                flash('Ошибка проверки прав доступа', 'danger')
                return redirect(url_for('jobs.index'))
            if data[0].get('role') != role:
                flash('Доступ запрещён', 'danger')
                return redirect(url_for('jobs.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def generate_csrf_token():
    """Сгенерировать CSRF-токен для сессии (если ещё нет)."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def csrf_protect(f):
    """Декоратор для защиты POST/PUT/DELETE маршрутов от CSRF-атак."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            token = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token')
            if not token or token != session.get('_csrf_token'):
                abort(400, description='CSRF-токен отсутствует или недействителен')
        return f(*args, **kwargs)
    return decorated
