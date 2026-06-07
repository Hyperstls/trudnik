import subprocess
from flask import Flask, session

from app.config import Config


import os

def create_app():
    # Корень проекта — родительская директория пакета app/
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    app = Flask(__name__,
                root_path=project_root,
                template_folder='templates',
                static_folder='static')
    app.config.from_object(Config)
    app.secret_key = app.config['SECRET_KEY']

    @app.context_processor
    def inject_global_user():
        return {'current_user_id': session.get('user_id')}

    @app.context_processor
    def inject_unread_notifications():
        """Глобальная переменная для бейджа уведомлений во всех шаблонах.
        Результат кешируется в сессии на 30 секунд для снижения нагрузки на Supabase."""
        from app.utils import supabase_request
        from time import time
        user_id = session.get('user_id')
        if user_id:
            cache_key = f'_notif_cache_{user_id}'
            cached = session.get(cache_key)
            now = time()
            if cached and (now - cached.get('ts', 0)) < 30:
                return {'unread_notifications': cached.get('count', 0)}
            resp = supabase_request('GET',
                f'notifications?user_id=eq.{user_id}&is_read=eq.false&select=id&limit=100')
            if resp.ok:
                data = resp.json()
                count = len(data) if isinstance(data, list) else 0
                session[cache_key] = {'count': count, 'ts': now}
                return {'unread_notifications': count}
            session[cache_key] = {'count': 0, 'ts': now}
        return {'unread_notifications': 0}

    # Кешируем git-версию при старте приложения (ранее вычислялась на каждый запрос)
    _git_version = 'dev'
    try:
        _git_version = subprocess.check_output(
            ['git', 'log', '-1', '--format=%h %s (%ai)'],
            cwd=project_root, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        pass

    @app.context_processor
    def inject_git_version():
        return {'git_version': _git_version}

    # Регистрация blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.profile import profile_bp
    from app.blueprints.jobs import jobs_bp
    from app.blueprints.applications import applications_bp
    from app.blueprints.shifts import shifts_bp
    from app.blueprints.chat import chat_bp
    from app.blueprints.favorites import favorites_bp
    from app.blueprints.blacklist import blacklist_bp
    from app.blueprints.notifications import notifications_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.monetization import monetization_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(shifts_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(favorites_bp)
    app.register_blueprint(blacklist_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(monetization_bp)

    # ================================
    # PWA / Google Play routes
    # ================================

    from flask import render_template, send_from_directory

    @app.route('/offline')
    def offline():
        """Offline fallback page for PWA service worker."""
        return render_template('offline.html')

    @app.route('/.well-known/assetlinks.json')
    def assetlinks():
        """Digital Asset Links for Trusted Web Activity (Google Play)."""
        return send_from_directory('static/.well-known', 'assetlinks.json',
                                   mimetype='application/json')

    # ── Обработчики ошибок ──────────────────────────────

    @app.errorhandler(404)
    def not_found(_e):
        return render_template('error.html', code=404,
                               message='Страница не найдена'), 404

    @app.errorhandler(500)
    def internal_error(_e):
        app.logger.exception('Internal server error')
        return render_template('error.html', code=500,
                               message='Внутренняя ошибка сервера'), 500

    return app


# Экземпляр приложения для WSGI/ASGI (Render, Gunicorn и совместимость)
app = create_app()
