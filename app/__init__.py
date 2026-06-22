import subprocess
import secrets
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from flask import Flask, g, session, request, abort, redirect, url_for

from app.config import Config


# ── Кеш версии с TTL 60 секунд ────────────────────────
@dataclass
class _VersionCache:
    value: str | None = None
    timestamp: float = 0.0

_git_version_cache = _VersionCache()


def get_git_version(project_root: str) -> str:
    """Получить актуальную git-версию приложения.

    Приоритет:
      1. Переменная окружения GIT_VERSION
      2. Файл VERSION в корне проекта
      3. git log -1 --format=%h %s (%ai)
      4. 'dev' (fallback)

    Результат кешируется на 60 секунд для снижения нагрузки.
    """
    now = time.time()
    if _git_version_cache.value is not None and (now - _git_version_cache.timestamp) < 60:
        return _git_version_cache.value

    version = os.environ.get('GIT_VERSION', '')

    if not version:
        version_file = os.path.join(project_root, 'VERSION')
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                version = f.read().strip()
        except Exception:
            pass

    if not version:
        try:
            version = subprocess.check_output(
                ['git', 'log', '-1', '--format=%h %s (%ai)'],
                cwd=project_root, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8'
            ).strip()
        except Exception:
            version = 'dev'

    _git_version_cache.value = version
    _git_version_cache.timestamp = now
    return version


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

    @app.context_processor
    def inject_csp_nonce():
        """Внедрение CSP nonce во все шаблоны для inline-скриптов."""
        return {'csp_nonce': getattr(g, 'csp_nonce', '')}

    @app.before_request
    def generate_csp_nonce():
        """Генерация случайного nonce для Content-Security-Policy."""
        g.csp_nonce = secrets.token_hex(24)

    @app.after_request
    def add_security_headers(response):
        """Добавить HTTP Security Headers для защиты от XSS, clickjacking, MIME sniffing."""
        nonce = getattr(g, 'csp_nonce', '')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic' https://cdn.jsdelivr.net https://api-maps.yandex.ru https://yastatic.net; "
            f"style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            f"font-src 'self' https://fonts.gstatic.com; "
            f"img-src 'self' data: https:; "
            f"connect-src 'self' https://*.supabase.co https://*.maps.yandex.net https://yastatic.net https://geocode-maps.yandex.ru https://fonts.googleapis.com https://fonts.gstatic.com ws://localhost:* wss://*; "
            f"worker-src 'self' blob:; "
            f"frame-src 'self'"
        )
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=self'
        # Cache-Control: статические ассеты кешируем на 24 часа, динамику — не кешируем
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=86400'
        else:
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.before_request
    def csrf_check():
        """Глобальная CSRF-защита: проверка токена для всех мутирующих запросов.
        Пропускаем: GET/HEAD/OPTIONS, тестовые запросы, auth-роуты (login/register).
        Приоритет: 1) X-CSRF-Token заголовок (fetch/AJAX), 2) _csrf_token в форме/JSON."""
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
        # Для обычных форм (устойчиво к не-form Content-Type, например text/plain)
        token = None
        try:
            token = request.form.get('_csrf_token')
        except Exception:
            pass
        # Если не в форме — пробуем JSON (для API-запросов с application/json)
        if not token and request.is_json:
            try:
                json_data = request.get_json(silent=True) or {}
                token = json_data.get('_csrf_token')
            except Exception:
                pass
        if not token or token != session.get('_csrf_token'):
            abort(400, description='CSRF-токен отсутствует или недействителен')

    @app.context_processor
    def inject_ws_config():
        """Добавляет WebSocket-конфигурацию и JWT-токен во все шаблоны."""
        config = {
            'wsUrl': os.environ.get('WEBSOCKET_URL', ''),
            'wsPort': os.environ.get('WEBSOCKET_PORT', '8001'),
            'pushEnabled': bool(os.environ.get('VAPID_PUBLIC_KEY', '')),
            'jwtToken': ''
        }

        # Генерируем JWT-токен для аутентифицированных пользователей
        user_id = session.get('user_id')
        if user_id:
            try:
                import jwt as pyjwt
                token = pyjwt.encode(
                    {
                        'user_id': str(user_id),
                        'exp': datetime.now(timezone.utc) + timedelta(days=7)
                    },
                    app.config['SECRET_KEY'],
                    algorithm='HS256'
                )
                config['jwtToken'] = token
            except Exception:
                pass  # Любая ошибка — не фатально

        return {'trudnik_ws_config': config}

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
        """Счётчик непрочитанных приглашений для трудника.

        Использует supabase_request с токеном пользователя вместо service_role.
        RLS-политика invitations разрешает SELECT для worker_id = auth.uid(),
        поэтому обход RLS не требуется.
        """
        from app.utils import supabase_request
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
            resp = supabase_request('GET',
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

    @app.context_processor
    def inject_git_version():
        """Версия вычисляется при каждом запросе (с TTL-кешем 60 с)."""
        return {
            'git_version': get_git_version(project_root),
            'worker_site_url': app.config.get('WORKER_SITE_URL', 'https://trudnik-hyperstls.amvera.io/'),
        }

    @app.context_processor
    def inject_sort_url():
        """Хелпер для построения URL сортировки с сохранением остальных параметров."""
        from urllib.parse import quote

        def sort_url(sort_value):
            args = dict(request.args)
            # Заменяем sort и сбрасываем page
            args['sort'] = sort_value
            args.pop('page', None)
            if not args:
                return '?'
            return '?' + '&'.join(f'{quote(str(k))}={quote(str(v))}' for k, v in args.items())

        return {'sort_url': sort_url}

    # Регистрация blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.profile import profile_bp
    from app.blueprints.jobs import jobs_bp
    from app.blueprints.jobs_api import jobs_api_bp
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
    app.register_blueprint(jobs_api_bp)
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
    # Редиректы для обратной совместимости
    # ================================

    @app.route('/jobs')
    def jobs_redirect():
        return redirect(url_for('jobs.index', tab='jobs'))

    @app.route('/search')
    def search_redirect():
        return redirect(url_for('jobs.index', tab='search'))

    # ================================
    # Jinja2-фильтры
    # ================================

    @app.template_filter('format_date')
    def format_date_filter(value):
        """Форматирует ISO-строку даты в человеко-читаемый вид на русском.
        Пример: '2026-06-16T00:47' → '16 июня 2026, 00:47'.
        Сегодняшние даты → 'Сегодня, 14:30', вчерашние → 'Вчера, 09:15'."""
        from app.utils import format_datetime
        return format_datetime(value)

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
        from werkzeug.exceptions import HTTPException
        # Пропускаем HTTP-исключения (abort, 404, 400 и т.д.) — возвращаем как есть
        if isinstance(e, HTTPException):
            return e
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

    # В тестовом режиме наполняем in-memory БД начальными данными
    if app.config.get('TESTING'):
        from app.utils import _seed_test_db
        _seed_test_db()

    return app


# Экземпляр приложения для WSGI/ASGI (Render, Gunicorn и совместимость)
app = create_app()
