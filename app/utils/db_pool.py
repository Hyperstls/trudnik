"""Connection pool для прямых подключений к PostgreSQL (psycopg2).

Используется для аварийных операций (fix-permissions, reset-users),
где требуется прямое подключение к БД в обход PostgREST.
"""

from psycopg2.pool import SimpleConnectionPool
import os

_pool = None


def get_pool():
    """Возвращает глобальный SimpleConnectionPool (ленивая инициализация).

    Returns:
        SimpleConnectionPool с minconn=1, maxconn=5.
    """
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            host=os.environ.get('DB_HOST', 'localhost'),
            port=os.environ.get('DB_PORT', '5432'),
            dbname=os.environ.get('DB_NAME', 'trudnik'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD', '')
        )
    return _pool


def get_connection():
    """Получить соединение из пула.

    Returns:
        psycopg2 connection object.
    """
    return get_pool().getconn()


def release_connection(conn):
    """Вернуть соединение в пул.

    Args:
        conn: psycopg2 connection object.
    """
    get_pool().putconn(conn)
