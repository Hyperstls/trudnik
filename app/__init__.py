import subprocess
import secrets
from flask import Flask, session, request, abort

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
    def inject_csrf_token():
        """Внедрение CSRF-токена во все шаблоны."""
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_hex(32)
        return {'csrf_token': session['_csrf_token']}

    @app.after_request
    def add_security_headers(response):
        """Добавить HTTP Security Headers для защиты от XSS, clickjacking, MIME sniffing."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://api-maps.yandex.ru https://yastatic.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://*.supabase.co https://*.maps.yandex.net https://yastatic.net https://geocode-maps.yandex.ru; frame-src 'self'"
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=self'
        return response

    @app.before_request
    def csrf_check():
        """Глобальная CSRF-защита: проверка токена для всех мутирующих запросов.
        Пропускаем: GET/HEAD/OPTIONS, тестовые запросы, auth-роуты (login/register).
        Приоритет: 1) X-CSRF-Token заголовок (fetch/AJAX), 2) _csrf_token в форме."""
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return
        # В режиме тестирования CSRF отключён
        if app.config.get('TESTING'):
            return
        # Пропускаем auth-роуты (login/register) — на них нет CSRF-токена в формах
        if request.path in ('/login', '/register'):
            return
        # Проверяем заголовок X-CSRF-Token (для fetch/AJAX-запросов)
        header_token = request.headers.get('X-CSRF-Token')
        if header_token:
            if header_token != session.get('_csrf_token'):
                abort(400, description='CSRF-токен недействителен')
            return
        # Для обычных форм
        token = request.form.get('_csrf_token')
        if not token or token != session.get('_csrf_token'):
            abort(400, description='CSRF-токен отсутствует или недействителен')

    @app.context_processor
    def inject_unread_notifications():
        """Глобальная переменная для бейджа уведомлений во всех шаблонах.
        Результат кешируется в сессии на 30 секунд.
        Исключает уведомления-приглашения (они на 👤+ иконке)."""
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
                f'notifications?user_id=eq.{user_id}&is_read=eq.false&select=id,type,message&limit=100')
            if resp.ok:
                data = resp.json()
                if isinstance(data, list):
                    # Исключаем уведомления "Вас пригласили" (приглашения трудника)
                    non_inv = [n for n in data if 'вас пригласили' not in (n.get('message') or '').lower()]
                    count = len(non_inv)
                else:
                    count = 0
                session[cache_key] = {'count': count, 'ts': now}
                return {'unread_notifications': count}
            session[cache_key] = {'count': 0, 'ts': now}
        return {'unread_notifications': 0}

    @app.context_processor
    def inject_pending_invitations():
        """Счётчик непрочитанных приглашений для трудника."""
        from app.utils import supabase_admin_request
        from time import time
        import logging
        log = logging.getLogger(__name__)
        user_id = session.get('user_id')
        role = session.get('role')
        log.debug('[INV_CTX] user_id=%s role=%s',
            str(user_id)[:12] if user_id else 'None', role)
        if user_id and role == 'worker':
            cache_key = f'_inv_cache_{user_id}'
            cached = session.get(cache_key)
            now = time()
            if cached and (now - cached.get('ts', 0)) < 30:
                log.debug('[INV_CTX] cached count=%d', cached.get('count', 0))
                return {'pending_invitations': cached.get('count', 0)}
            resp = supabase_admin_request('GET',
                f'invitations?worker_id=eq.{user_id}&status=eq.pending&select=id&limit=100')
            if resp.ok:
                data = resp.json()
                count = len(data) if isinstance(data, list) else 0
                log.debug('[INV_CTX] query ok, count=%d', count)
            else:
                count = 0
                log.error('[INV_CTX] query FAILED: status=%s body=%s',
                          resp.status_code, (resp.text or '')[:200])
            session[cache_key] = {'count': count, 'ts': now}
            return {'pending_invitations': count}
        log.debug('[INV_CTX] skip: no user_id or not worker')
        return {'pending_invitations': 0}

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
    from app.blueprints.chat import chat_bp
    from app.blueprints.favorites import favorites_bp
    from app.blueprints.blacklist import blacklist_bp
    from app.blueprints.notifications import notifications_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.ratings import ratings_bp
    from app.blueprints.seo import seo_bp
    from app.blueprints.employers import employers_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(favorites_bp)
    app.register_blueprint(blacklist_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ratings_bp)
    app.register_blueprint(seo_bp)
    app.register_blueprint(employers_bp)

    # ================================
    # API-роуты accept/reject/reopen (вынесены на объект app
    # из-за проблем с blueprint-роутингом на production/Render)
    # ================================
    from app.blueprints.applications import api_handle_application
    from app.decorators import login_required
    from app.utils import rate_limit

    @app.route('/api/applications/<app_id>/accept', methods=['POST'])
    @login_required
    @rate_limit
    def api_accept_application(app_id):
        return api_handle_application(app_id, 'accept')

    @app.route('/api/applications/<app_id>/reject', methods=['POST'])
    @login_required
    @rate_limit
    def api_reject_application(app_id):
        return api_handle_application(app_id, 'reject')

    @app.route('/api/applications/<app_id>/reopen', methods=['POST'])
    @login_required
    def api_reopen_application(app_id):
        return api_handle_application(app_id, 'reopen')

    # ================================
    # PWA / Google Play routes
    # ================================

    from flask import render_template, send_from_directory

    @app.route('/sw.js')
    def service_worker():
        return app.send_static_file('sw.js')

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

    @app.before_request
    def log_static_requests():
        """Диагностический лог: отслеживание запросов к /static/ для поиска 500."""
        if request.path.startswith('/static/'):
            app.logger.info('Static request: %s | method=%s | user_agent=%s',
                            request.path, request.method,
                            request.headers.get('User-Agent', 'unknown')[:120])

    @app.route('/static/')
    def static_directory_redirect():
        """Запрос /static/ без имени файла → 404 вместо 500.
        Предотвращает внутреннюю ошибку Flask при попытке открыть директорию как файл."""
        app.logger.warning('Static directory listing requested: %s', request.path)
        abort(404)

    @app.errorhandler(404)
    def not_found(_e):
        return render_template('error.html', error_code='404',
                               error='Страница не найдена'), 404

    @app.errorhandler(500)
    def internal_error(_e):
        app.logger.exception('Internal server error')
        return render_template('error.html', error_code='500',
                               error='Внутренняя ошибка сервера'), 500

    @app.errorhandler(Exception)
    def handle_supabase_error(e):
        import requests as req_lib
        if isinstance(e, req_lib.ConnectionError):
            return render_template('error.html', error_code='503',
                                   error='Сервис временно недоступен. Пожалуйста, попробуйте позже.'), 503
        if hasattr(e, '__module__') and 'supabase' in str(e.__module__).lower():
            return render_template('error.html', error_code='503',
                                   error='Сервис временно недоступен. Пожалуйста, попробуйте позже.'), 503
        raise e

    # ================================
    # Health Check Endpoint
    # ================================

    from flask import jsonify
    from app.utils import supabase_request

    @app.route('/health')
    def health_check():
        """Проверка работоспособности приложения и доступности БД."""
        try:
            resp = supabase_request('GET', 'profiles?select=id&limit=1')
            if resp.ok:
                return jsonify({"status": "healthy", "database": "connected"}), 200
            else:
                return jsonify({"status": "unhealthy", "database": "disconnected"}), 503
        except Exception:
            return jsonify({"status": "unhealthy"}), 500

    return app


# Экземпляр приложения для WSGI/ASGI (Render, Gunicorn и совместимость)
app = create_app()
