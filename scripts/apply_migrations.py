#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для автоматического применения SQL-миграций к Supabase через REST API.

Использование:
    # Показать доступные миграции
    python apply_migrations.py

    # Применить конкретную миграцию
    python apply_migrations.py migrations/030_fix_schema_gaps.sql

    # Применить все пронумерованные миграции
    python apply_migrations.py --all

Зависимости:
    - python-dotenv (чтение .env)
    - httpx (HTTP-клиент)
    - Стандартная библиотека Python
"""

import io
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
import httpx

# ---------------------------------------------------------------------------
# Принудительная UTF-8 для вывода (Windows)
# ---------------------------------------------------------------------------
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ---------------------------------------------------------------------------
# Загрузка конфигурации
# ---------------------------------------------------------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = 60  # секунд на один statement

# ---------------------------------------------------------------------------
# SQL-парсер: разбиение на отдельные statement'ы
# ---------------------------------------------------------------------------


def split_sql_statements(sql: str) -> list[str]:
    """
    Разбивает SQL-текст на отдельные statement'ы по символу ';'.

    Учитывает:
      - Строки в одинарных кавычках ('...')
      - Строки в двойных кавычках ("...")  (идентификаторы)
      - Dollar-quoted строки ($$...$$ или $tag$...$tag$)
      - Однострочные комментарии (-- ...)
      - Многострочные комментарии (/* ... */)
      - Вложенность скобок (не разбивает внутри (...), даже если там есть ';')

    Возвращает список непустых statement'ов (каждый уже без завершающей ';',
    с обрезанными пробелами по краям).
    """
    statements: list[str] = []
    current: list[str] = []
    paren_depth = 0
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]

        # --- Однострочный комментарий -- ... до конца строки ---
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            # Ищем конец строки
            newline = sql.find("\n", i)
            if newline == -1:
                # Всё до конца файла — комментарий
                break
            # Включаем символ новой строки в current (чтобы номера строк
            # совпадали, если кому-то понадобится)
            current.append(sql[i:newline + 1])
            i = newline + 1
            continue

        # --- Многострочный комментарий /* ... */ ---
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            end = sql.find("*/", i + 2)
            if end == -1:
                # Незакрытый комментарий до конца файла
                break
            current.append(sql[i:end + 2])
            i = end + 2
            continue

        # --- Dollar-quoted строка: $$...$$ или $tag$...$tag$ ---
        if ch == "$":
            tag_end = sql.find("$", i + 1)
            if tag_end != -1:
                # Полный открывающий тег: от i до tag_end включительно
                open_tag = sql[i:tag_end + 1]  # например, "$$" или "$func$"
                # Ищем следующий такой же тег (закрывающий)
                close_pos = sql.find(open_tag, tag_end + 1)
                if close_pos != -1:
                    # Включаем весь dollar-quoted блок как есть
                    block_end = close_pos + len(open_tag)
                    current.append(sql[i:block_end])
                    i = block_end
                    continue
            # Не нашли закрывающий тег — обрабатываем $ как обычный символ
            current.append(ch)
            i += 1
            continue

        # --- Одинарная кавычка (строковой литерал) ---
        if ch == "'":
            current.append(ch)
            i += 1
            while i < n:
                c = sql[i]
                current.append(c)
                if c == "'":
                    # Удвоенная кавычка '' — экранированная кавычка внутри строки
                    if i + 1 < n and sql[i + 1] == "'":
                        current.append("'")
                        i += 2
                        continue
                    # Конец строки
                    i += 1
                    break
                i += 1
            continue

        # --- Двойная кавычка (идентификатор) ---
        if ch == '"':
            current.append(ch)
            i += 1
            while i < n:
                c = sql[i]
                current.append(c)
                if c == '"':
                    if i + 1 < n and sql[i + 1] == '"':
                        current.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue

        # --- Скобки (отслеживаем глубину) ---
        if ch == "(":
            paren_depth += 1
            current.append(ch)
            i += 1
            continue
        if ch == ")":
            if paren_depth > 0:
                paren_depth -= 1
            current.append(ch)
            i += 1
            continue

        # --- Точка с запятой на верхнем уровне → граница statement'а ---
        if ch == ";" and paren_depth == 0:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        # --- Обычный символ ---
        current.append(ch)
        i += 1

    # Остаток (без завершающей ';')
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


# ---------------------------------------------------------------------------
# Предпросмотр statement'а (первая значащая строка)
# ---------------------------------------------------------------------------
def preview_statement(sql: str, max_len: int = 90) -> str:
    """Возвращает краткое описание statement'а для вывода прогресса."""
    # Берём первую непустую строку, убираем ведущие пробелы
    for line in sql.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            if len(stripped) > max_len:
                return stripped[:max_len - 3] + "..."
            return stripped
    # Если все строки — комментарии, берём первую непустую
    for line in sql.split("\n"):
        stripped = line.strip()
        if stripped:
            if len(stripped) > max_len:
                return stripped[:max_len - 3] + "..."
            return stripped
    return "(empty)"


# ---------------------------------------------------------------------------
# Выполнение одного statement'а через RPC exec_sql
# ---------------------------------------------------------------------------
def execute_statement(
    client: httpx.Client, sql: str
) -> tuple[bool, str]:
    """
    Выполняет один SQL-statement через Supabase RPC exec_sql.

    Returns:
        (True, "OK")                  — успех
        (False, "HTTP 400: ...")      — ошибка с деталями
    """
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    payload = {"sql_query": sql}

    try:
        resp = client.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code in (200, 201, 204):
            return True, "OK"
        else:
            # Пытаемся извлечь сообщение об ошибке
            detail = ""
            try:
                body = resp.json()
                detail = body.get("message", body.get("hint", str(body)))
            except Exception:
                detail = resp.text[:300]
            return False, f"HTTP {resp.status_code}: {detail}"
    except httpx.TimeoutException:
        return False, "Timeout"
    except httpx.RequestError as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Применение одного файла миграции
# ---------------------------------------------------------------------------
def apply_migration_file(filepath: str, client: httpx.Client) -> int:
    """
    Применяет одну миграцию из SQL-файла.

    Returns:
        Количество ошибок (0 = всё успешно).
    """
    path = Path(filepath)
    if not path.exists():
        print(f"ОШИБКА: Файл не найден: {filepath}")
        return 1

    print(f"\n{'=' * 60}")
    print(f"=== Применение миграции: {path.name} ===")
    print(f"Подключение к Supabase: {SUPABASE_URL}")

    sql_content = path.read_text(encoding="utf-8")
    statements = split_sql_statements(sql_content)

    # Фильтруем пустые и чисто-комментарные statement'ы
    meaningful = []
    for stmt in statements:
        # Убираем строки, которые состоят только из комментариев
        lines = [l.strip() for l in stmt.split("\n")]
        non_comment_lines = [
            l for l in lines if l and not l.startswith("--")
        ]
        if non_comment_lines:
            meaningful.append(stmt)

    total = len(meaningful)
    print(f"Найдено statement'ов: {total}\n")

    errors: list[tuple[int, str, str]] = []  # (номер, preview, ошибка)
    success = 0

    for idx, stmt in enumerate(meaningful, 1):
        preview = preview_statement(stmt)
        ok, msg = execute_statement(client, stmt)

        counter = f"[{idx:02d}/{total:02d}]"
        if ok:
            print(f"{counter} OK:    {preview}")
            success += 1
        else:
            print(f"{counter} ERROR: {preview}")
            print(f"        -> {msg}")
            errors.append((idx, preview, msg))

    # Сводка
    print(f"\n{'=' * 60}")
    if errors:
        print(f"=== ГОТОВО: {success}/{total} успешно, {len(errors)} ошибок ===")
        print("\nСписок ошибок:")
        for num, prev, msg in errors:
            print(f"  [{num:02d}] {prev}")
            print(f"       {msg}")
    else:
        print(f"=== ГОТОВО: {success}/{total} успешно, 0 ошибок ===")

    return len(errors)


# ---------------------------------------------------------------------------
# Список доступных миграций
# ---------------------------------------------------------------------------
def list_migrations() -> None:
    """Выводит список доступных SQL-миграций в папке migrations/."""
    if not MIGRATIONS_DIR.exists():
        print(f"Папка миграций не найдена: {MIGRATIONS_DIR}")
        return

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("Миграции не найдены.")
        return

    # Разделяем на пронумерованные и именованные
    numbered = []
    named = []
    for f in files:
        if re.match(r"^\d{3}_", f.name):
            numbered.append(f)
        else:
            named.append(f)

    print(f"\nДоступные миграции в {MIGRATIONS_DIR}/:\n")

    if numbered:
        print("Пронумерованные миграции:")
        for f in numbered:
            # Извлекаем описание из имени файла
            desc = f.stem[4:].replace("_", " ")
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name:<45s} {size_kb:5.1f} KB  {desc}")
        print()

    if named:
        print("Именованные миграции:")
        for f in named:
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name:<45s} {size_kb:5.1f} KB")

    if not numbered and not named:
        print("  (нет .sql файлов)")

    print(f"\nВсего: {len(files)} файл(ов)")
    print("\nИспользование:")
    print("  python apply_migrations.py migrations/030_fix_schema_gaps.sql")
    print("  python apply_migrations.py --all")


# ---------------------------------------------------------------------------
# Применение всех пронумерованных миграций
# ---------------------------------------------------------------------------
def apply_all_migrations(client: httpx.Client) -> None:
    """Применяет все пронумерованные миграции по порядку."""
    if not MIGRATIONS_DIR.exists():
        print(f"Папка миграций не найдена: {MIGRATIONS_DIR}")
        return

    files = sorted(
        f for f in MIGRATIONS_DIR.glob("*.sql")
        if re.match(r"^\d{3}_", f.name)
    )

    if not files:
        print("Нет пронумерованных миграций для применения.")
        return

    total_files = len(files)
    total_errors = 0

    print(f"\n{'#' * 60}")
    print(f"### ПАКЕТНОЕ ПРИМЕНЕНИЕ: {total_files} миграций ###")
    print(f"### Подключение: {SUPABASE_URL}")
    print(f"{'#' * 60}")

    for idx, f in enumerate(files, 1):
        print(f"\n--- Миграция {idx}/{total_files}: {f.name} ---")
        errors = apply_migration_file(str(f), client)
        total_errors += errors

    print(f"\n{'#' * 60}")
    print(f"### ВСЕГО: {total_files} миграций, ошибок в сумме: {total_errors} ###")
    print(f"{'#' * 60}")


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
def main() -> None:
    # Проверка конфигурации
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("ОШИБКА: SUPABASE_URL и SUPABASE_SERVICE_ROLE_KEY должны быть в .env")
        sys.exit(1)

    # Разбор аргументов
    if len(sys.argv) < 2:
        list_migrations()
        return

    arg = sys.argv[1]

    if arg == "--all":
        with httpx.Client() as client:
            apply_all_migrations(client)
    elif arg in ("-h", "--help"):
        print(__doc__)
        list_migrations()
    else:
        # Считаем, что передан путь к файлу миграции
        with httpx.Client() as client:
            errors = apply_migration_file(arg, client)
        sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
