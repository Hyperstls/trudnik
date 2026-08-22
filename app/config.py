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
    logger.debug('PGRST_JWT_SECRET loaded: length=%d', len(PGRST_JWT_SECRET))
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

    YANDEX_MAPS_API_KEY = os.environ.get('YANDEX_MAPS_API_KEY') or os.environ.get('YANDEX_GEOCODER_KEY', '')
    WORKER_SITE_URL = os.environ.get('WORKER_SITE_URL', 'https://trudnik-hyperstls.amvera.io/')

    # Cookie Security (B9: Secure cookie flags)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = os.environ.get('DEPLOYMENT_ENV', 'development') in ('production', 'staging')
    SESSION_COOKIE_SAMESITE = 'Strict'  # Защита от CSRF
    SESSION_COOKIE_NAME = 'trudnik_session'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 МБ — anti-DDoS (ограничение тела запроса)
    GLOBAL_RATE_LIMIT_PER_MIN = int(os.environ.get('GLOBAL_RATE_LIMIT_PER_MIN', '120'))
    PERMANENT_SESSION_LIFETIME = 3600  # 1 час

    # Server-side sessions in Redis (D5: replaces client-side SecureCookieSession)
    # Сессии хранятся в Redis, кука содержит только session_id.
    # Преимущества: отзыв сессий, нет утечки данных в куку, TTL на стороне сервера.
    SESSION_TYPE = 'redis'
    SESSION_PERMANENT = True
    SESSION_USE_SIGNER = True  # Подпись session_id в куке (доп. защита от подделки)
    SESSION_KEY_PREFIX = 'session:'  # Префикс ключей в Redis
    SESSION_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

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
    SMTP_USER = os.environ.get('SMTP_USER') or os.environ.get('SMTP_USERNAME', '')
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
    # Примечание: лимиты @rate_limit декоратора конфигурируются через env
    # RATE_LIMIT_MAX_REQUESTS / RATE_LIMIT_WINDOW (app/utils/rate_limit_decorator.py)
    # Phase 3 (Часть B): авто-заморозка по жалобам
    REPORT_FREEZE_THRESHOLD = int(os.environ.get('REPORT_FREEZE_THRESHOLD', '3'))
    REPORT_FREEZE_WINDOW_HOURS = int(os.environ.get('REPORT_FREEZE_WINDOW_HOURS', '24'))
    # Phase 3 (Часть A): верификация через мессенджер MAX.
    # Telegram отключён (152-ФЗ ст. 12 — трансграничная передача, 2026-08).
    MAX_BOT_TOKEN = os.environ.get('MAX_BOT_TOKEN', '')
    MAX_BOT_USERNAME = os.environ.get('MAX_BOT_USERNAME', 'se13803803_bot')
    CACHE_MAX_SIZE = 256
    PAGINATION_DEFAULT_PER_PAGE = 20

    # Phase 3 (Часть A): верификация через мессенджер — таймауты и endpoint'ы
    MESSENGER_VERIFY_TTL = int(os.environ.get('MESSENGER_VERIFY_TTL', '600'))  # сек, TTL одноразового токена
    MESSENGER_API_TIMEOUT = int(os.environ.get('MESSENGER_API_TIMEOUT', '10'))  # сек, HTTP-таймаут к API MAX
    MAX_API_URL = os.environ.get('MAX_API_URL', 'https://platform-api2.max.ru')

    # PostgREST-клиент: HTTP-таймауты (сек)
    POSTGREST_TIMEOUT = int(os.environ.get('POSTGREST_TIMEOUT', '30'))
    POSTGREST_RPC_TIMEOUT = int(os.environ.get('POSTGREST_RPC_TIMEOUT', '60'))
    POSTGREST_HEALTH_TIMEOUT = int(os.environ.get('POSTGREST_HEALTH_TIMEOUT', '5'))

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
    # Публичный WS-URL для клиентов. Если WEBSOCKET_PUBLIC_URL не задан,
    # используем WEBSOCKET_URL (имя переменной, которое задано в проде).
    # Применяется в /api/ws/token (wsUrl), CSP connect-src и TRUDNIK_CONFIG.
    WEBSOCKET_PUBLIC_URL = (
        os.environ.get('WEBSOCKET_PUBLIC_URL', '')
        or os.environ.get('WEBSOCKET_URL', '')
    )

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
