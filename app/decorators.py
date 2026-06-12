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


