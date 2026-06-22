import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    TESTING = os.environ.get('TESTING', 'False').lower() in ('true', '1', 'yes')
    _FALLBACK_SECRET = os.environ.get('SECRET_KEY')
    if not _FALLBACK_SECRET:
        raise RuntimeError('SECRET_KEY environment variable is required')
    SECRET_KEY = _FALLBACK_SECRET

    # Amvera PostgREST
    _default_postgrest = 'http://localhost:3000' if os.environ.get('FLASK_ENV') != 'production' else ''
    POSTGREST_URL = os.environ.get('POSTGREST_URL', _default_postgrest)
    if os.environ.get('FLASK_ENV') == 'production' and not POSTGREST_URL:
        raise RuntimeError('POSTGREST_URL is required in production')
    PGRST_JWT_SECRET = os.environ.get('PGRST_JWT_SECRET', '')
    if os.environ.get('FLASK_ENV') == 'production' and not PGRST_JWT_SECRET:
        raise RuntimeError('PGRST_JWT_SECRET is required in production')

    YANDEX_MAPS_API_KEY = os.environ.get('YANDEX_MAPS_API_KEY', '')
    WORKER_SITE_URL = os.environ.get('WORKER_SITE_URL', 'https://trudnik-hyperstls.amvera.io/')

    # Cookie Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV', '') == 'production'
    SESSION_COOKIE_SAMESITE = 'Lax'

    # ═══════════════════════════════════════════════════════════
    # Инфраструктура реального времени (уведомления v2)
    # ═══════════════════════════════════════════════════════════
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    WEBSOCKET_PORT = int(os.environ.get('WEBSOCKET_PORT', '8001'))
    WEBSOCKET_URL = os.environ.get('WEBSOCKET_URL', 'ws://localhost:8001/ws')

    # ═══════════════════════════════════════════════════════════
    # SMTP / Email-рассылка
    # ═══════════════════════════════════════════════════════════
    SMTP_HOST = os.environ.get('SMTP_HOST', 'localhost')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USER = os.environ.get('SMTP_USER', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', 'True').lower() in ('true', '1', 'yes')
    SMTP_USE_SSL = os.environ.get('SMTP_USE_SSL', 'False').lower() in ('true', '1', 'yes')
    SMTP_TIMEOUT = int(os.environ.get('SMTP_TIMEOUT', '30'))
    SMTP_FROM_EMAIL = os.environ.get('SMTP_FROM_EMAIL', 'notifications@trudnik.ru')
    SMTP_FROM_NAME = os.environ.get('SMTP_FROM_NAME', 'Trudnik')
    SMTP_DAILY_LIMIT = int(os.environ.get('SMTP_DAILY_LIMIT', '1000'))
    SMTP_RATE_LIMIT_PAUSE = float(os.environ.get('SMTP_RATE_LIMIT_PAUSE', '1.0'))

    # ═══════════════════════════════════════════════════════════
    # Бизнес-константы (этап 2.2)
    # ═══════════════════════════════════════════════════════════
    DEFAULT_LAT = 55.75
    DEFAULT_LNG = 37.61
    MAX_BATCH_SIZE = 50
    MAX_PHOTO_SIZE_MB = int(os.environ.get('MAX_PHOTO_SIZE_MB', '5'))
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads'))
    RATE_LIMIT_MAX = 10
    RATE_LIMIT_WINDOW = 60
    PERMANENT_SESSION_LIFETIME = 1800  # 30 минут — сессия переживает задержки Supabase
    CACHE_MAX_SIZE = 256
    PAGINATION_DEFAULT_PER_PAGE = 20

    # ═══════════════════════════════════════════════════════════
    # Web Push API (VAPID-ключи)
    # ═══════════════════════════════════════════════════════════
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
    VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'notifications@trudnik.ru')
    VAPID_CLAIMS_SUBJECT = os.environ.get('VAPID_CLAIMS_SUBJECT', 'mailto:notifications@trudnik.ru')

    @property
    def DATABASE_URL(self):
        """Формирует PostgreSQL DSN из отдельных переменных окружения."""
        pg_user = os.environ.get('PGUSER')
        pg_password = os.environ.get('PGPASSWORD')
        pg_host = os.environ.get('PGHOST')
        pg_port = os.environ.get('PGPORT', '5432')
        pg_database = os.environ.get('PGDATABASE')
        # Если есть DATABASE_URL — используем его напрямую
        if direct_url := os.environ.get('DATABASE_URL'):
            return direct_url
        # Если нет ни одной переменной — не формируем URL (не используется)
        if not any([pg_user, pg_password, pg_host, pg_database]):
            return ''
        # Если есть хотя бы одна — требуем все
        missing = [v for v in ['PGUSER', 'PGPASSWORD', 'PGHOST', 'PGDATABASE'] 
                   if not os.environ.get(v)]
        if missing:
            raise RuntimeError(f'Missing database env vars: {", ".join(missing)}')
        return f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
