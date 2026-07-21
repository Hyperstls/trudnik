#!/usr/bin/env python3
"""
Автоматическое применение SQL-миграций для проекта Trudnik.
================================================================
Подключается к PostgreSQL, отслеживает уже применённые миграции
в таблице ``_migrations`` и последовательно (по алфавиту имён файлов)
выполняет новые ``.sql``-файлы из папки ``migrations/``.

Каждый файл выполняется в отдельной транзакции: при ошибке транзакция
откатывается, а скрипт завершается с кодом 1.

Использование
-------------
Ручной запуск (Windows / Linux)::

    python scripts/apply_migrations.py

Dry-run (только показать, что будет применено, без выполнения)::

    python scripts/apply_migrations.py --dry-run

Настройка Cron Job на Amvera
-----------------------------
В интерфейсе Amvera создайте Cron Job со следующей командой::

    cd /app && python scripts/apply_migrations.py

Или, если нужно явно передать переменную окружения::

    cd /app && DATABASE_ADMIN_URL=postgresql://user:pass@host:port/dbname python scripts/apply_migrations.py

Требования
----------
- ``DATABASE_ADMIN_URL`` или ``DATABASE_URL`` в переменных окружения (формат: ``postgresql://user:pass@host:port/dbname``)
  Приоритет: ``DATABASE_ADMIN_URL`` (пользователь с SUPERUSER), затем ``DATABASE_URL`` (fallback).
- ``psycopg2`` (синхронный драйвер, не psycopg2-binary)
- Python 3.9+
"""

import hashlib
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("apply_migrations")

# ---------------------------------------------------------------------------
# Проверка наличия psycopg2 (даём понятную ошибку, если не установлен)
# ---------------------------------------------------------------------------
try:
    import psycopg2  # noqa: E402
except ImportError:
    logger.error(
        "Библиотека psycopg2 не установлена. Установите её командой:\n"
        "    pip install psycopg2"
    )
    sys.exit(1)


# ===================================================================
# Вспомогательные функции
# ===================================================================


def get_database_url() -> str:
    """Получить URL базы данных из переменных окружения.

    Приоритет: ``DATABASE_ADMIN_URL`` (пользователь с SUPERUSER),
    затем ``DATABASE_URL`` (обычный пользователь).

    Returns
    -------
    str
        Строка подключения PostgreSQL.

    Raises
    ------
    SystemExit(1)
        Если ни одна переменная не установлена или пуста.
    """
    url = os.environ.get('DATABASE_ADMIN_URL') or os.environ.get('DATABASE_URL', '').strip()
    if not url:
        logger.error(
            "Ни одна из переменных окружения не установлена:\n"
            "  DATABASE_ADMIN_URL (рекомендуется для миграций, требует SUPERUSER)\n"
            "  DATABASE_URL (fallback)\n"
            "Установите одну из них перед запуском:\n"
            "  Linux/Mac:  export DATABASE_ADMIN_URL=postgresql://user:pass@host:port/dbname\n"
            "  Windows:    set DATABASE_ADMIN_URL=postgresql://user:pass@host:port/dbname\n"
            "  Amvera:     добавьте переменную DATABASE_ADMIN_URL в настройках проекта"
        )
        sys.exit(1)
    return url


def get_migrations_dir() -> Path:
    """Получить путь к папке ``migrations/`` относительно расположения скрипта.

    Скрипт находится в ``scripts/``, миграции — в ``migrations/`` на уровне
    корня проекта (на один уровень выше).

    Returns
    -------
    Path
        Абсолютный путь к директории с миграциями.

    Raises
    ------
    SystemExit(1)
        Если директория не существует.
    """
    script_dir = Path(__file__).resolve().parent  # scripts/
    migrations_dir = script_dir.parent / "migrations"
    if not migrations_dir.is_dir():
        logger.error("Папка migrations не найдена: %s", migrations_dir)
        sys.exit(1)
    return migrations_dir


def compute_sha256(filepath: Path) -> str:
    """Вычислить SHA256-хеш содержимого файла.

    Parameters
    ----------
    filepath : Path
        Путь к файлу.

    Returns
    -------
    str
        Hex-строка хеша (64 символа).
    """
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# ===================================================================
# Работа с БД
# ===================================================================


def create_tracking_table(conn: "psycopg2.extensions.connection") -> None:
    """Создать tracking-таблицу ``_migrations``, если её ещё нет.

    Таблица хранит имя файла миграции, временную метку применения и
    SHA256-хеш содержимого — для аудита и предотвращения повторного
    выполнения.

    Parameters
    ----------
    conn : psycopg2 connection
        Открытое соединение с PostgreSQL (autocommit=False).
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                filename   TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT now(),
                checksum   TEXT
            );
        """)
    conn.commit()
    logger.info("Tracking-таблица _migrations готова.")


def get_applied_migrations(conn: "psycopg2.extensions.connection") -> set:
    """Вернуть множество имён уже применённых файлов миграций.

    Parameters
    ----------
    conn : psycopg2 connection
        Открытое соединение.

    Returns
    -------
    set of str
        Имена файлов (например, ``"001_setup_rls.sql"``), уже записанные
        в ``_migrations``.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT filename FROM _migrations;")
        return {row[0] for row in cur.fetchall()}


def apply_migration(
    conn: "psycopg2.extensions.connection",
    filepath: Path,
) -> None:
    """Применить один файл миграции в отдельной транзакции.

    Содержимое файла и запись в ``_migrations`` выполняются в одной
    транзакции: либо и то и другое фиксируется, либо ничего.

    Parameters
    ----------
    conn : psycopg2 connection
        Открытое соединение.
    filepath : Path
        Путь к ``.sql``-файлу.

    Raises
    ------
    psycopg2.Error
        Если выполнение SQL завершилось ошибкой (транзакция будет
        откатана вызывающим кодом).
    """
    filename = filepath.name
    checksum = compute_sha256(filepath)

    logger.info("Применяю миграцию: %s (SHA256: %s)", filename, checksum)

    sql = filepath.read_text(encoding="utf-8")

    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO _migrations (filename, checksum) VALUES (%s, %s);",
            (filename, checksum),
        )

    conn.commit()
    logger.info("Миграция %s успешно применена.", filename)


def collect_migrations(
    migrations_dir: Path,
    applied: set,
) -> list:
    """Собрать список новых ``.sql``-файлов, отсортированных по алфавиту.

    Parameters
    ----------
    migrations_dir : Path
        Путь к директории с миграциями.
    applied : set of str
        Имена уже применённых миграций.

    Returns
    -------
    list of Path
        Файлы, которые ещё не были применены, в алфавитном порядке.
    """
    # Применяем только пронумерованные миграции NNN[_a-z]_*.sql (напр. 067_.., 077b_..).
    # Ад-hoc файлы (manual_fix_all.sql, run_all_safe.sql, apply_manual_pgadmin.sql) игнорируются.
    import re
    mig_re = re.compile(r'^\d{3}[a-z]?_.*\.sql$', re.IGNORECASE)
    all_files = sorted(
        f for f in migrations_dir.iterdir()
        if f.is_file() and f.suffix.lower() == ".sql" and mig_re.match(f.name)
    )
    return [f for f in all_files if f.name not in applied]


# ===================================================================
# Точка входа
# ===================================================================


def main() -> None:
    """Основная логика скрипта."""
    dry_run = "--dry-run" in sys.argv

    # --- Ранний выход: миграции отключены по умолчанию ---
    # Авто-мигратор отключён для всех автоматических запусков
    # (Cron Job, Amvera CI). Для ручного запуска установите:
    #   MIGRATIONS_ENABLED=true python scripts/apply_migrations.py
    if os.environ.get("MIGRATIONS_ENABLED", "").lower() not in ("true", "1", "yes"):
        logger.info(
            "Миграции отключены (MIGRATIONS_ENABLED не установлена). "
            "Для принудительного запуска: MIGRATIONS_ENABLED=true python scripts/apply_migrations.py"
        )
        return

    if dry_run:
        logger.info("=== DRY RUN: миграции НЕ будут применены ===")

    # 1. Проверить переменные окружения и пути
    database_url = get_database_url()
    migrations_dir = get_migrations_dir()

    logger.info("Папка миграций: %s", migrations_dir)

    # 2. Подключиться к PostgreSQL
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = False
        logger.info("Подключение к PostgreSQL установлено.")
    except psycopg2.Error as exc:
        logger.error("Не удалось подключиться к PostgreSQL: %s", exc)
        sys.exit(1)

    try:
        # 3. Создать tracking-таблицу
        create_tracking_table(conn)

        # 4. Получить уже применённые миграции
        applied = get_applied_migrations(conn)
        logger.info("Уже применено миграций: %d", len(applied))

        # 5. Собрать новые файлы
        new_files = collect_migrations(migrations_dir, applied)

        if not new_files:
            logger.info("Новых миграций нет — всё актуально.")
            return

        logger.info("Новых миграций к применению: %d", len(new_files))
        for fp in new_files:
            logger.info("  -> %s", fp.name)

        if dry_run:
            logger.info("=== DRY RUN завершён (ничего не применено) ===")
            return

        # 6. Применить каждую миграцию
        for filepath in new_files:
            try:
                apply_migration(conn, filepath)
            except psycopg2.Error as exc:
                logger.error(
                    "Ошибка при применении миграции %s: %s",
                    filepath.name, exc,
                )
                conn.rollback()
                logger.error(
                    "Применение миграций остановлено. "
                    "Предыдущие успешные миграции НЕ откатываются "
                    "(каждая фиксируется независимо)."
                )
                sys.exit(1)

        logger.info(
            "Все миграции (%d шт.) успешно применены.", len(new_files)
        )

    finally:
        conn.close()
        logger.info("Соединение с PostgreSQL закрыто.")


if __name__ == "__main__":
    main()
