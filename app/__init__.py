"""Trudnik Flask Application Factory — create_app() < 100 строк."""
import os
import time as _time_module
from flask import Flask
from app.config import Config

_app_start_time = _time_module.time()


def create_app():
    """Создать и настроить Flask-приложение."""
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    app = Flask(__name__, root_path=project_root,
                template_folder='templates', static_folder='static')
    app.config.from_object(Config)
    app.secret_key = app.config['SECRET_KEY']

    from app.utils.logging_config import setup_json_logging
    setup_json_logging()

    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # Диагностика PGRST_JWT_SECRET
    _jwt_secret = app.config.get('PGRST_JWT_SECRET', '') or os.environ.get('PGRST_JWT_SECRET', '')
    if _jwt_secret:
        _jwt_len = len(_jwt_secret.encode('utf-8'))
        app.logger.info('PGRST_JWT_SECRET: %d байт (%s)', _jwt_len,
                        'OK' if _jwt_len >= 32 else 'СЛИШКОМ КОРОТКИЙ')
    else:
        app.logger.warning('PGRST_JWT_SECRET не задан! Использую SECRET_KEY — небезопасно.')

    from app.middleware import register_middleware; register_middleware(app)
    from app.context_processors import register_context_processors; register_context_processors(app)
    from app.error_handlers import register_error_handlers; register_error_handlers(app)

    # Blueprints
    from app.blueprints.auth import auth_bp
    from app.blueprints.profile import profile_bp
    from app.blueprints.jobs import jobs_bp
    from app.blueprints.jobs_api import jobs_api_bp
    from app.blueprints.applications import applications_bp
    from app.blueprints.chat import chat_bp
    from app.blueprints.favorites import favorites_bp
    from app.blueprints.blacklist import blacklist_bp
    from app.blueprints.notifications import notifications_bp
    from app.blueprints.admin_dashboard import admin_dashboard_bp
    from app.blueprints.admin_users import admin_users_bp
    from app.blueprints.admin_jobs import admin_jobs_bp
    from app.blueprints.admin_dictionaries import admin_dictionaries_bp
    from app.blueprints.admin_verification import admin_verification_bp
    from app.blueprints.admin_diagnostics import admin_diagnostics_bp
    from app.blueprints.ratings import ratings_bp
    from app.blueprints.seo import seo_bp
    from app.blueprints.employers import employers_bp
    from app.blueprints.core import core_bp
    from app.blueprints.messenger_verify import messenger_bp
    from app.blueprints.faq import faq_bp

    _all_bps = [core_bp, auth_bp, profile_bp, jobs_bp, jobs_api_bp, applications_bp,
                chat_bp, favorites_bp, blacklist_bp, notifications_bp,
                admin_dashboard_bp, admin_users_bp, admin_jobs_bp,
                admin_dictionaries_bp, admin_verification_bp, admin_diagnostics_bp,
                ratings_bp, seo_bp, employers_bp, messenger_bp, faq_bp]
    for bp in _all_bps:
        app.register_blueprint(bp)

    # ═══ Anti-DDoS: глобальный rate-limit по IP (все методы, все эндпоинты) ═══
    @app.before_request
    def _global_ip_rate_limit():
        """Ограничение запросов по IP: GLOBAL_RATE_LIMIT_PER_MIN (120/мин по умолчанию).
        Статика и health/ready исключены. Fail-open при недоступности Redis."""
        from flask import jsonify, request
        if app.config.get('TESTING'):
            return  # в тестах — без глобального rate-limit (mock Redis)
        if request.path.startswith('/static/') or request.path in ('/health', '/ready', '/favicon.ico'):
            return
        ip = (request.headers.get('X-Forwarded-For', '') or request.remote_addr or '').split(',')[0].strip()
        if not ip or ip == 'unknown':
            return
        try:
            from app.utils.redis_client import get_redis_client
            r = get_redis_client()
            if not r:
                return
            key = f'iprl:{ip}'
            count = r.incr(key)
            if count == 1:
                r.expire(key, 60)
            limit = app.config.get('GLOBAL_RATE_LIMIT_PER_MIN', 120)
            if count > limit:
                return jsonify({'error': 'Слишком много запросов. Попробуйте позже.'}), 429
        except Exception:
            logging.getLogger(__name__).debug('global rate-limit: Redis error (fail-open)', exc_info=True)

    @app.template_filter('format_date')
    def _format_date(value):
        from app.utils import format_date
        return format_date(value)

    @app.template_filter('format_datetime')
    def _format_datetime(value):
        from app.utils import format_datetime
        return format_datetime(value)

    # Redis для rate limiting
    from app.utils.redis_client import get_redis_client
    redis_client = get_redis_client()
    if redis_client is not None:
        try:
            redis_client.ping()
        except Exception:
            app.logger.warning('Redis ping failed')
    app.redis = redis_client

    # Server-side сессии в Redis (D5: Flask-Session заменяет client-side SecureCookieSession).
    # В mock/test-режиме (POSTGREST_MOCK_MODE) оставляем дефолтные cookie-сессии Flask —
    # unit-тесты не должны зависеть от Redis (модуль redis там замокан).
    if os.environ.get('POSTGREST_MOCK_MODE', '').lower() not in ('1', 'true', 'yes'):
        try:
            import redis as _redis_lib
            _sess_url = app.config.get('SESSION_REDIS_URL') or app.config.get('REDIS_URL')
            # Без decode_responses: Flask-Session хранит pickled-бинарик; клиент должен
            # возвращать bytes.
            app.config['SESSION_REDIS'] = _redis_lib.from_url(_sess_url)
            from flask_session import Session
            Session(app)
            app.logger.info('Server-side Redis sessions enabled (D5)')
        except Exception as _sess_err:
            app.logger.warning(
                'Redis session backend init failed, fallback to cookie sessions: %s',
                _sess_err,
            )

    if app.config.get('TESTING'):
        from app.utils import _seed_test_db
        _seed_test_db()

    return app
