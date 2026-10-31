"""Настройки Django-компаньона «Трудник».

Работает поверх СУЩЕСТВУЮЩЕЙ схемы PostgreSQL (unmanaged-модели, см. core/models.py).
Секреты — только из окружения; локально подхватывается .env корня репозитория.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent        # djadmin/
REPO_ROOT = BASE_DIR.parent                              # корень репозитория

# Локальная разработка: берём .env репозитория (в .gitignore). На Amvera переменные
# приходят от платформы, файла нет — load_dotenv просто ничего не сделает.
load_dotenv(REPO_ROOT / ".env")

# Fail-safe: без явного DEPLOYMENT_ENV считаем продакшен (DEBUG off, SECRET_KEY
# обязателен). Локальная разработка задаёт development в .env.
DEPLOYMENT_ENV = os.getenv("DEPLOYMENT_ENV", "production")
DEBUG = DEPLOYMENT_ENV == "development"
PROD = not DEBUG

# Пароль отдаёт окружение; фолбэк — только DEBUG-режим локальной разработки.
_dev_fallback_key = "trudnik-dj-local-dev-key"
SECRET_KEY = os.getenv("SECRET_KEY") or (_dev_fallback_key if DEBUG else "")
if PROD and not SECRET_KEY:
    raise RuntimeError("SECRET_KEY обязателен в production (env)")

# ── Хосты / CSRF ────────────────────────────────────────────────────────────
_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "")
ALLOWED_HOSTS = (
    [h.strip() for h in _hosts.split(",") if h.strip()]
    if _hosts
    else (["*"] if DEBUG else ["xn--d1aigknli.xn--p1ai", ".amvera.tech", "localhost", "127.0.0.1"])
)
_origins = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = (
    [o.strip() for o in _origins.split(",") if o.strip()]
    if _origins
    else ["https://xn--d1aigknli.xn--p1ai", "https://*.amvera.tech", "http://localhost:8000", "http://127.0.0.1:8000"]
)

# ── База данных ─────────────────────────────────────────────────────────────
def _database_url() -> dict:
    """DJANGO_DATABASE_URL (приоритет — своя роль БД) → DATABASE_URL (как у Flask)
    → PG*-переменные. %-декодирование паролей."""
    from urllib.parse import unquote, urlsplit

    url = os.getenv("DJANGO_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    if not url:
        pg = {k: os.getenv(k, "") for k in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE")}
        if pg["PGHOST"] and pg["PGUSER"]:
            return {
                "NAME": pg["PGDATABASE"] or "trudnik",
                "USER": pg["PGUSER"],
                "PASSWORD": pg["PGPASSWORD"],
                "HOST": pg["PGHOST"],
                "PORT": pg["PGPORT"] or "5432",
            }
        # docker-compose по умолчанию (локальная разработка)
        return {"NAME": "trudnik", "USER": "trudnik", "PASSWORD": "trudnik_dev", "HOST": "localhost", "PORT": "5433"}  # pragma: allowlist secret (docker-compose dev-креды)
    parts = urlsplit(url)
    return {
        "NAME": parts.path.lstrip("/") or "trudnik",
        "USER": unquote(parts.username or "trudnik"),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "localhost",
        "PORT": str(parts.port or 5432),
    }


_db = _database_url()
if _db["HOST"] == "db":  # compose-алиас из .env; снаружи контейнера БД на localhost:5433
    _db = {**_db, "HOST": "localhost", "PORT": "5433"}
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DJANGO_DB_NAME", _db["NAME"]),
        "USER": _db["USER"],
        "PASSWORD": _db["PASSWORD"],
        "HOST": _db["HOST"],
        "PORT": _db["PORT"],
        "CONN_MAX_AGE": 60,
        "TEST": {
            # Тесты идут против клона dev-БД (scripts/dj_test_clone.py создаёт
            # trudnik_test по шаблону trudnik: в клоне живут триггеры и RPC).
            "NAME": "trudnik_test",
            "SERIALIZE": False,
        },
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# user_skills/job_skills: составной PK без суррогатного id — primary_key на FK
# даёт fields.W342, это осознанный маппинг unmanaged-таблиц (запись — raw SQL).
SILENCED_SYSTEM_CHECKS = ["fields.W342"]

# ── Приложения ──────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "core",
]
AUTH_USER_MODEL = "core.Profile"
AUTHENTICATION_BACKENDS = ["core.auth_backend.ProfileBackend"]

# Пароли: Profile сам переопределяет set_password/check_password на сырой bcrypt
# (совместимость с Flask/pgcrypto — см. core/models.py); этот список — запасной
# путь для make_password при случайном использовании.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.AdminIpAllowlistMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context.notifications_unread",
            ]
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

# ── Статика ─────────────────────────────────────────────────────────────────
# Публичные страницы используют уже скомпилированный Tailwind из Flask-части
# (freshness-гейт Flask сканирует только корневые templates/ и static/js/).
STATIC_URL = "/static/"
STATICFILES_DIRS = [REPO_ROOT / "static"]
STATIC_ROOT = Path(os.getenv("DJANGO_STATIC_ROOT", "/data/static" if PROD else BASE_DIR / "_static"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # manifest-хэши включаются явно (Dockerfile: DJANGO_WHITENOISE_MANIFEST=1 после
    # collectstatic); dev/тесты работают на plain-статике
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if os.getenv("DJANGO_WHITENOISE_MANIFEST") == "1"
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/data/uploads" if PROD else str(BASE_DIR / "_uploads"))

# Абсолютизация /uploads/... (файлы лежат в volume Flask-сервиса).
WORKER_SITE_URL = os.getenv("WORKER_SITE_URL", "").rstrip("/")

# ── Безопасность ────────────────────────────────────────────────────────────
if PROD:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# Админка: опциональный IP-allowlist (аналог ADMIN_API_ALLOWED_IPS у Flask).
DJANGO_ADMIN_ALLOWED_IPS = [
    ip.strip() for ip in os.getenv("DJANGO_ADMIN_ALLOWED_IPS", "").split(",") if ip.strip()
]

LOGIN_URL = "/login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/jobs"

# ── Email (SMTP из env; без SMTP_HOST — console-бэкенд для dev) ────────────
_smtp_host = os.getenv("SMTP_HOST", "")
if _smtp_host:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = _smtp_host
    EMAIL_PORT = int(os.getenv("SMTP_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("SMTP_USERNAME", "")
    EMAIL_HOST_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    EMAIL_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    EMAIL_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "notifications@trudnik.ru")

# ── Кэш (токены мессенджер-верификации и пр.; Redis при наличии REDIS_URL) ──
_redis_url = os.getenv("REDIS_URL", "")
if _redis_url and ("://redis:" in _redis_url or "@redis:" in _redis_url):
    # compose-алиас из .env; снаружи контейнера — localhost (docker-compose мапит порт)
    _redis_url = _redis_url.replace("://redis:", "://localhost:").replace("@redis:", "@localhost:")
if _redis_url:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                          "LOCATION": _redis_url}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# ── VAPID (Web Push) ────────────────────────────────────────────────────────
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "notifications@trudnik.ru")

# ── Channels (WebSocket-чат; Redis channel layer при REDIS_URL) ─────────────
if _redis_url:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer",
                                  "CONFIG": {"hosts": [_redis_url]}}}
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# ── Метрики (X-Metrics-Token; прод без токена → 404) ───────────────────────
METRICS_TOKEN = os.getenv("METRICS_TOKEN", "")

# ── MAX Bot API (мессенджер-верификация; webhook fail-closed без секрета) ────
MAX_WEBHOOK_SECRET = os.getenv("MAX_WEBHOOK_SECRET", "")
MAX_BOT_USERNAME = os.getenv("MAX_BOT_USERNAME", "")

# ── Yandex SmartCaptcha (включена при наличии серверного ключа; fail-closed) ─
SMARTCAPTCHA_SERVER_KEY = os.getenv("SMARTCAPTCHA_SERVER_KEY", "")
SMARTCAPTCHA_CLIENT_KEY = os.getenv("SMARTCAPTCHA_CLIENT_KEY", "")

# ── Локализация ─────────────────────────────────────────────────────────────
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

# ── Логирование ─────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
}
