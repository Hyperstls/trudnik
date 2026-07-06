"""Сервис аутентификации — логин, rate-limit, блокировки аккаунтов.

Вынесен из app/blueprints/auth.py для разделения бизнес-логики и HTTP-слоя.
"""

import logging
import os

from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Database URL
# ═══════════════════════════════════════════════════════════════

def get_db_url() -> str:
    """Получить URL для прямого подключения к PostgreSQL.

    Приоритет:
    1. DATABASE_URL из переменных окружения
    2. PGDATABASE_URL
    3. Config.DATABASE_URL (собранный из PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE)
    4. Отдельные переменные PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE
    """
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('PGDATABASE_URL', '')
    if db_url:
        logger.debug("login: using DATABASE_URL from env: %s",
                     db_url[:db_url.index('@') + 1] + '***' if '@' in db_url else db_url)
        return db_url
    # Fallback на Config.DATABASE_URL (собирается из отдельных PG-переменных)
    from app.config import Config
    config_url = Config.DATABASE_URL
    if config_url:
        logger.debug("login: using Config.DATABASE_URL: %s",
                     config_url[:config_url.index('@') + 1] + '***' if '@' in config_url else config_url)
        return config_url
    # Последняя попытка — собрать из отдельных переменных
    pg_user = os.environ.get('PGUSER', '')
    pg_password = os.environ.get('PGPASSWORD', '')
    pg_host = os.environ.get('PGHOST', '')
    pg_port = os.environ.get('PGPORT', '5432')
    pg_database = os.environ.get('PGDATABASE', '')
    if all([pg_user, pg_password, pg_host, pg_database]):
        return f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
    logger.warning("login: no DATABASE_URL configured (env DATABASE_URL, PGDATABASE_URL, "
                   "or PGUSER/PGPASSWORD/PGHOST/PGDATABASE)")
    return ''


# ═══════════════════════════════════════════════════════════════
# Login methods
# ═══════════════════════════════════════════════════════════════

def login_direct_sql(email: str, password: str) -> dict | None:
    """Проверить email/password через прямое SQL-подключение (в обход PostgREST RPC).

    Использует pgcrypto crypt() для проверки хеша пароля.
    Возвращает dict с {user_id, email, role, full_name} или None при ошибке/неверном пароле.

    При ошибке подключения выбрасывает исключение с понятным описанием,
    чтобы вызывающий код мог попробовать fallback (PostgREST).
    """
    db_url = get_db_url()
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL не задан. Установите переменную окружения DATABASE_URL "
            "или PGUSER/PGPASSWORD/PGHOST/PGPORT/PGDATABASE."
        )
    try:
        import psycopg2
        conn = None
        try:
            conn = psycopg2.connect(db_url, connect_timeout=10)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("""
                SELECT id, email, role, full_name, COALESCE(email_verified, false)
                FROM profiles
                WHERE email = %s AND password_hash = crypt(%s, password_hash)
            """, (email, password))
            row = cur.fetchone()
            cur.close()
            if row:
                return {'user_id': str(row[0]), 'email': row[1], 'role': row[2],
                        'full_name': row[3], 'email_verified': row[4]}
            logger.info("login: invalid credentials for %s (direct SQL)", email)
            return None
        finally:
            if conn:
                conn.close()
    except ImportError:
        logger.error("login: psycopg2 not installed — cannot use direct SQL")
        raise RuntimeError(
            "psycopg2 не установлен. Установите: pip install psycopg2-binary"
        )
    except Exception as e:
        logger.error("login: direct SQL connection failed for %s: %s", email, e)
        raise RuntimeError(
            f"Не удалось подключиться к БД напрямую: {e}. "
            f"Проверьте DATABASE_URL (порт, хост, пароль). "
            f"PostgreSQL должен быть доступен."
        )


def login_postgrest(email: str, password: str) -> dict | None:
    """Fallback: проверить email/password через PostgREST RPC login_user.

    Используется если прямой SQL недоступен (например, нет psycopg2 или БД не на локалхосте).
    Возвращает dict с {user_id, email, role, full_name} или None при ошибке/неверном пароле.
    """
    try:
        from app.utils import postgrest_admin_request
        resp = postgrest_admin_request('POST', 'rpc/login_user', data={
            'p_email': email,
            'p_password': password
        })
        if resp and resp.ok:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                user = data[0]
                return {
                    'user_id': str(user.get('id', user.get('user_id', ''))),
                    'email': user.get('email', email),
                    'role': user.get('role', 'worker'),
                    'full_name': user.get('full_name', ''),
                    'email_verified': user.get('email_verified', False)
                }
            elif isinstance(data, dict):
                return {
                    'user_id': str(data.get('id', data.get('user_id', ''))),
                    'email': data.get('email', email),
                    'role': data.get('role', 'worker'),
                    'full_name': data.get('full_name', ''),
                    'email_verified': data.get('email_verified', False)
                }
        logger.info("login: invalid credentials for %s (PostgREST fallback)", email)
        return None
    except Exception as e:
        logger.error("login: PostgREST fallback also failed for %s: %s", email, e)
        return None


# ═══════════════════════════════════════════════════════════════
# Login rate-limit / lockout (C22)
# ═══════════════════════════════════════════════════════════════

def is_login_locked_out(lockout_key: str) -> bool:
    """Проверить, заблокирован ли аккаунт по ключу блокировки."""
    try:
        client = get_redis_client()
        if client is None:
            return False
        return client.exists(lockout_key) > 0
    except Exception:
        return False


def increment_login_attempts(lockout_key: str, attempts_key: str, email: str) -> None:
    """Инкрементировать счётчик. При 5 попытках — exponential backoff."""
    try:
        client = get_redis_client()
        if client is None:
            return
        attempts = client.incr(attempts_key)
        if attempts == 1:
            client.expire(attempts_key, 900)
        if attempts >= 5:
            # Exponential backoff: 1-я блокировка 15 мин, 2-я 30, 3-я 60, 4-я 240
            lockout_count_key = f"login_lockout_count:{email}"
            lockout_count = int(client.get(lockout_count_key) or 0)
            lockout_duration = 900 * (2 ** lockout_count)
            client.setex(lockout_key, lockout_duration, str(lockout_count + 1))
            client.delete(attempts_key)
            logger.warning('Account locked: %s for %d sec (attempt %d)',
                           email, lockout_duration, lockout_count + 1)
    except Exception as e:
        logger.warning('Failed: %s', e)


def clear_login_attempts(lockout_key: str, attempts_key: str, email: str = None) -> None:
    """Сбросить счётчик и блокировку после успешного входа."""
    try:
        client = get_redis_client()
        if client is None:
            return
        client.delete(attempts_key, lockout_key)
        if email:
            client.delete(f"login_lockout_count:{email}")
    except Exception:
        pass