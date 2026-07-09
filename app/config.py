import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    TESTING = os.environ.get('TESTING', 'False').strip().lower() in ('true', '1', 'yes')
    _FALLBACK_SECRET = os.environ.get('SECRET_KEY')
    if not _FALLBACK_SECRET:
        raise RuntimeError('SECRET_KEY environment variable is required')
    SECRET_KEY = _FALLBACK_SECRET

    # Amvera PostgREST
    _default_postgrest = 'http://localhost:3000' if os.environ.get('DEPLOYMENT_ENV') != 'production' else ''
    POSTGREST_URL = os.environ.get('POSTGREST_URL', _default_postgrest).strip()

    # Нормализация URL: добавляем http:// если схема отсутствует
    if POSTGREST_URL and not POSTGREST_URL.startswith(('http://', 'https://')):
        logger.warning(
            f'POSTGREST_URL не содержит схемы: "{POSTGREST_URL}". '
            f'Добавлено "http://" по умолчанию.'
        )
        POSTGREST_URL = 'http://' + POSTGREST_URL

    if os.environ.get('DEPLOYMENT_ENV') == 'production' and not POSTGREST_URL:
        raise RuntimeError('POSTGREST_URL is required in production')

    if not POSTGREST_URL:
        POSTGREST_URL = 'http://localhost:3000'
        logger.warning('POSTGREST_URL не задан, установлен fallback: http://localhost:3000')
    PGRST_JWT_SECRET = os.environ.get('PGRST_JWT_SECRET', '').strip()
    logger.debug('PGRST_JWT_SECRET loaded: length=%d, first_chars=%s',
                 len(PGRST_JWT_SECRET), PGRST_JWT_SECRET[:16] + '...' if len(PGRST_JWT_SECRET) > 16 else PGRST_JWT_SECRET)
    if not PGRST_JWT_SECRET:
        logger.error(
            "PGRST_JWT_SECRET не задан! Будет использован SECRET_KEY как fallback "
            "— это небезопасно для production"
        )
    if os.environ.get('DEPLOYMENT_ENV') == 'production' and not PGRST_JWT_SECRET:
        raise RuntimeError('PGRST_JWT_SECRET is required in production')

    # ═══════════════════════════════════════════════════════════
    # Admin API Token (C8)
    # ═══════════════════════════════════════════════════════════
    ADMIN_API_TOKEN = os.environ.get('ADMIN_API_TOKEN', '')
    DEPLOYMENT_ENV = os.environ.get('DEPLOYMENT_ENV', 'development')
    if DEPLOYMENT_ENV == 'production' and not ADMIN_API_TOKEN:
        raise ValueError("ADMIN_API_TOKEN must be set in production")

    # ═══════════════════════════════════════════════════════════
    # Монетизация (C9)
    # ═══════════════════════════════════════════════════════════
    MONETIZATION_ENABLED = os.environ.get('MONETIZATION_ENABLED', 'false').lower() == 'true'

    # ═══════════════════════════════════════════════════════════
    # Валидация длины PGRST_JWT_SECRET
    # ═══════════════════════════════════════════════════════════
    _deployment_env = os.environ.get('DEPLOYMENT_ENV', 'development')
    _jwt_secret_bytes = len(PGRST_JWT_SECRET.encode('utf-8'))
    if _jwt_secret_bytes < 32:
        _msg = (
            f'PGRST_JWT_SECRET слишком короткий: {_jwt_secret_bytes} байт. '
            f'Минимальная рекомендуемая длина для HS256 — 32 байта (256 бит).'
        )
        if _deployment_env == 'production':
            logger.error('PRODUCTION SECURITY: ' + _msg)
        else:
            logger.warning('SECURITY: ' + _msg)
    elif _jwt_secret_bytes < 64:
        _msg = (
            f'PGRST_JWT_SECRET: {_jwt_secret_bytes} байт — '
            f'достаточно для HS256 (мин. 32), но рекомендуется 64 байта (512 бит).'
        )
        logger.info(_msg)

    YANDEX_MAPS_API_KEY = os.environ.get('YANDEX_GEOCODER_KEY', '')
    WORKER_SITE_URL = os.environ.get('WORKER_SITE_URL', 'https://trudnik-hyperstls.amvera.io/')

    # Cookie Security (B9: Secure cookie flags)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True  # Только HTTPS
    SESSION_COOKIE_SAMESITE = 'Strict'  # Защита от CSRF
    SESSION_COOKIE_NAME = 'trudnik_session'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 часа (в секундах)

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
    SMTP_USER = os.environ.get('SMTP_USERNAME', '')
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
    PERMANENT_SESSION_LIFETIME = 1800  # 30 минут — сессия переживает задержки PostgREST (Amvera) — Supabase не используется (устарело)
    CACHE_MAX_SIZE = 256
    PAGINATION_DEFAULT_PER_PAGE = 20

    # ═══════════════════════════════════════════════════════════
    # Circuit Breaker (этап 4.1)
    # ═══════════════════════════════════════════════════════════
    CB_FAILURE_THRESHOLD = int(os.getenv('CB_FAILURE_THRESHOLD', '10'))
    CB_RECOVERY_TIMEOUT = int(os.getenv('CB_RECOVERY_TIMEOUT', '60'))

    # ═══════════════════════════════════════════════════════════
    # Web Push API (VAPID-ключи)
    # ═══════════════════════════════════════════════════════════
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
    VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'notifications@trudnik.ru')
    VAPID_CLAIMS_SUBJECT = os.environ.get('VAPID_CLAIMS_SUBJECT', 'mailto:notifications@trudnik.ru')

    WEBSOCKET_JWT_SECRET = os.environ.get('WEBSOCKET_JWT_SECRET', '')
    if os.environ.get('DEPLOYMENT_ENV') in ('production', 'staging') and not WEBSOCKET_JWT_SECRET:
        raise RuntimeError('WEBSOCKET_JWT_SECRET is required in production')
    WEBSOCKET_PUBLIC_URL = os.environ.get('WEBSOCKET_PUBLIC_URL', '')

    _direct = os.environ.get('DATABASE_URL')
    if _direct:
        DATABASE_URL = _direct.strip()
    else:
        _pg_user = os.environ.get('PGUSER')
        _pg_password = os.environ.get('PGPASSWORD')
        _pg_host = os.environ.get('PGHOST')
        _pg_port = os.environ.get('PGPORT', '5432')
        _pg_database = os.environ.get('PGDATABASE')
        if all([_pg_user, _pg_password, _pg_host, _pg_database]):
            DATABASE_URL = f"postgresql://{_pg_user}:{_pg_password}@{_pg_host}:{_pg_port}/{_pg_database}"
        else:
            DATABASE_URL = ''

    # Блокировка test-режима в production
    if os.environ.get('DEPLOYMENT_ENV') in ('production', 'staging'):
        if os.environ.get('POSTGREST_MOCK_MODE', '').lower() in ('1', 'true', 'yes'):
            raise RuntimeError('FATAL: POSTGREST_MOCK_MODE is set in production! Refusing to start.')
        if os.environ.get('TEST_USER_PASSWORD'):
            raise RuntimeError('FATAL: TEST_USER_PASSWORD is set in production! Refusing to start.')
