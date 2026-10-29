#!/usr/bin/env python
"""Пересоздание тестовой БД trudnik_test как клона dev-БД trudnik.

В клоне живут триггеры (recompute_profile_rating, updated_at, tsvector) и
SECURITY DEFINER RPC — тесты прогоняются по-настоящему, включая RPC.

Использование (нужен запущенный `docker compose up -d db`):
    .venv/Scripts/python.exe scripts/dj_test_clone.py
    .venv/Scripts/python.exe djadmin/manage.py test core --keepdb -v 1
"""
import os
import re
import sys
from pathlib import Path

import psycopg2

REPO = Path(__file__).resolve().parent.parent

# тот же приоритет, что у djadmin/config/settings.py
if not _url and (REPO / ".env").exists():
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip().rstrip("\r")
        m2 = re.match(r"^DATABASE_URL=([^#]+)$", line)
        if m2 and not line.startswith("#"):
            _url = m2.group(1).strip().strip('"').strip("'")
            break

from urllib.parse import unquote, urlsplit

parts = urlsplit(_url) if _url else None
if parts and parts.hostname:
    USER, PASSWORD, HOST = (
        unquote(parts.username or "trudnik"),
        unquote(parts.password or ""),
        parts.hostname,
    )
    PORT = str(parts.port or 5432)
    DBNAME = parts.path.lstrip("/") or "trudnik"
else:
    # docker-compose по умолчанию
    USER = os.getenv("PGUSER", "trudnik")
    PASSWORD = os.getenv("PGPASSWORD", "trudnik_dev")
    HOST = os.getenv("PGHOST", "localhost")
    PORT = os.getenv("PGPORT", "5433")
    DBNAME = os.getenv("PGDATABASE", "trudnik")

if HOST == "db":  # compose-алиас из .env; снаружи контейнера БД на localhost:5433
    HOST, PORT = "localhost", "5433"

TEST_DB = "trudnik_test"


def main() -> int:
    conn = psycopg2.connect(dbname=DBNAME, user=USER, password=PASSWORD, host=HOST, port=PORT)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname IN (%s, %s) AND pid <> pg_backend_pid()",
                (TEST_DB, DBNAME),
            )
            cur.execute(f'DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)')
            cur.execute(f'CREATE DATABASE {TEST_DB} TEMPLATE {DBNAME}')
            cur.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public'"
            )
            tables = cur.fetchone()[0]
        print(f"OK: {TEST_DB} создана как клон {DBNAME} (public: {tables} таблиц).")
        print(f"Дальше: .venv/Scripts/python.exe djadmin/manage.py test core --keepdb -v 1")
        return 0
    except psycopg2.OperationalError as exc:
        print(f"НЕ УДАЛОСЬ: {exc}", file=sys.stderr)
        print("Подними БД: docker compose up -d db", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
