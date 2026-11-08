"""Репетиция процедуры backup/restore БД на локальном docker-стенде.

Делает pg_dump работающей dev-БД (контейнер `trudnik-db`), восстанавливает дамп
в отдельную scratch-БД `<db>_restore_check`, сверяет count(*) ключевых таблиц
и удаляет scratch-БД. Source-БД не изменяется.

Прод-процедура — docs/RESTORE_RUNBOOK.md. Скрипт не подключается к проду
и не печатает пароли.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_TABLES = (
    "profiles",
    "jobs",
    "applications",
    "messages",
    "ratings",
    "site_pages",
    "schema_migrations",
)
SCRATCH_SUFFIX = "_restore_check"
IDENT_RE = re.compile(r"[a-z0-9_]+")


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """docker CLI с отключённой MSYS-конвертацией путей (иначе /tmp ломается)."""
    env = dict(os.environ)
    env["MSYS_NO_PATHCONV"] = "1"
    proc = subprocess.run(
        ["docker", *args], capture_output=True, text=True, encoding="utf-8", env=env
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"docker {' '.join(args)}: {detail}")
    return proc


def psql(container: str, user: str, database: str, sql: str) -> str:
    return docker(
        "exec", container, "psql", "-U", user, "-d", database, "-tAc", sql
    ).stdout.strip()


def table_count(container: str, user: str, database: str, table: str) -> int:
    raw = psql(
        container, user, database, f'SELECT count(*) FROM "{table}"'
    )
    if not re.fullmatch(r"\d+", raw or ""):
        raise RuntimeError(f"не удалось получить count(*) для {table}: {raw!r}")
    return int(raw)


def drop_scratch(container: str, user: str, scratch: str) -> None:
    psql(
        container,
        user,
        "postgres",
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{scratch}'",
    )
    psql(container, user, "postgres", f'DROP DATABASE IF EXISTS "{scratch}"')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default=os.getenv("REHEARSAL_CONTAINER", "trudnik-db"))
    parser.add_argument("--user", default=os.getenv("POSTGRES_USER", "trudnik"))
    parser.add_argument("--database", default=os.getenv("POSTGRES_DB", "trudnik"))
    parser.add_argument(
        "--dump-dir", default=None,
        help="куда положить дамп; явный каталог сохраняется (по умолчанию temp удаляется)",
    )
    parser.add_argument("--keep-dump", action="store_true", help="не удалять дамп после сверки")
    parser.add_argument(
        "--tables", default=",".join(DEFAULT_TABLES),
        help="список таблиц для сверки через запятую",
    )
    args = parser.parse_args()

    database = args.database.strip()
    scratch = f"{database}{SCRATCH_SUFFIX}"
    tables = [t.strip() for t in args.tables.split(",") if t.strip()]

    # Guard: никогда не восстанавливаем поверх source, не трогаем чужие имена
    # и не подставляем произвольный SQL (имена идут в кавычки/литералы).
    if (
        not database
        or not IDENT_RE.fullmatch(database)
        or scratch == database
        or not scratch.endswith(SCRATCH_SUFFIX)
    ):
        print("FAIL: недопустимое имя scratch-БД (разрешены [a-z0-9_])", file=sys.stderr)
        return 1
    bad_tables = [t for t in tables if not IDENT_RE.fullmatch(t)]
    if not tables or bad_tables:
        print(f"FAIL: недопустимый список таблиц: {bad_tables or 'пусто'}", file=sys.stderr)
        return 1

    try:
        running = docker(
            "inspect", "-f", "{{.State.Running}}", args.container
        ).stdout.strip()
    except RuntimeError as exc:
        print(f"FAIL: контейнер недоступен: {exc}", file=sys.stderr)
        return 1
    if running != "true":
        print(f"FAIL: контейнер {args.container} не запущен", file=sys.stderr)
        return 1

    dump_dir = Path(args.dump_dir) if args.dump_dir else Path(tempfile.mkdtemp(prefix="trudnik-restore-"))
    dump_dir.mkdir(parents=True, exist_ok=True)
    local_dump = dump_dir / f"{database}.dump"
    remote_dump = f"/tmp/{database}-rehearsal.dump"
    started = time.monotonic()
    scratch_created = False
    cleanup_failed = False
    code = 0

    try:
        print(f"[1/5] dump {database} → {local_dump}")
        docker("exec", args.container, "pg_dump", "-U", args.user, "-d", database,
               "-Fc", "-f", remote_dump)
        docker("cp", f"{args.container}:{remote_dump}", str(local_dump))
        size_mb = local_dump.stat().st_size / (1024 * 1024)
        print(f"      dump: {size_mb:.1f} MB")

        print(f"[2/5] recreate scratch DB {scratch}")
        drop_scratch(args.container, args.user, scratch)
        psql(args.container, args.user, "postgres", f'CREATE DATABASE "{scratch}"')
        scratch_created = True

        print(f"[3/5] restore → {scratch}")
        docker("cp", str(local_dump), f"{args.container}:{remote_dump}")
        docker("exec", args.container, "pg_restore", "-U", args.user, "-d", scratch,
               "--no-owner", "--no-acl", remote_dump)

        print("[4/5] verify row counts")
        mismatches = []
        for table in tables:
            source_count = table_count(args.container, args.user, database, table)
            restored_count = table_count(args.container, args.user, scratch, table)
            mark = "OK" if source_count == restored_count else "MISMATCH"
            print(f"      {mark:8} {table}: source={source_count} restored={restored_count}")
            if source_count != restored_count:
                mismatches.append(table)
        if mismatches:
            print(f"FAIL: расхождение count(*) в таблицах: {', '.join(mismatches)}", file=sys.stderr)
            code = 1
        else:
            elapsed = time.monotonic() - started
            print(f"[5/5] OK: backup+restore+verify за {elapsed:.1f} с")
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        code = 1
    finally:
        try:
            docker("exec", args.container, "rm", "-f", remote_dump)
        except RuntimeError:
            pass
        if scratch_created:
            try:
                drop_scratch(args.container, args.user, scratch)
                print(f"      scratch DB {scratch} удалена")
            except RuntimeError as exc:
                cleanup_failed = True
                print(f"FAIL: не удалось удалить scratch DB: {exc}", file=sys.stderr)
        if not args.keep_dump and args.dump_dir is None:
            shutil.rmtree(dump_dir, ignore_errors=True)

    return 1 if cleanup_failed else code


if __name__ == "__main__":
    raise SystemExit(main())
