#!/usr/bin/env python3
"""
Сборщик метаданных из Supabase для сверки с кодом и миграциями.
Выводит структуру БД в JSON-файл supabase_schema.json.

Использование:
    python dump_supabase_schema.py

Требования:
    - .env файл с SUPABASE_URL, SUPABASE_KEY (anon), SUPABASE_SERVICE_ROLE_KEY
    - python-dotenv, requests (из requirements.txt)
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
OUTPUT_FILE = BASE_DIR / "supabase_schema.json"
FALLBACK_SQL_FILE = BASE_DIR / "supabase_schema_queries.sql"

# SQL-запросы для каждой секции
QUERIES: Dict[str, str] = {
    "tables": """
        SELECT table_name, column_name, data_type, is_nullable, column_default, character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """,
    "rls_status": """
        SELECT tablename, rowsecurity AS rls_enabled
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
    """,
    "rls_policies": """
        SELECT tablename, policyname, cmd AS operation
        FROM pg_policies
        WHERE schemaname = 'public'
        ORDER BY tablename, policyname
    """,
    "indexes": """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
    """,
    "enums": """
        SELECT typname, enum_range(oid::regtype)::text[] AS enum_values
        FROM pg_type
        WHERE typtype = 'e'
    """,
}

# RPC-функция, которую мы ожидаем найти в БД (может называться иначе)
RPC_EXEC_SQL_NAMES = [
    "exec_sql",
    "execute_sql",
    "run_sql",
    "query_sql",
]


# ---------------------------------------------------------------------------
# Вспомогательные утилиты
# ---------------------------------------------------------------------------


def load_env() -> Tuple[str, str, str]:
    """Читает .env и возвращает (SUPABASE_URL, SUPABASE_KEY, SERVICE_ROLE_KEY)."""
    if not ENV_FILE.exists():
        print(f"[ОШИБКА] Файл .env не найден по пути: {ENV_FILE}")
        sys.exit(1)

    load_dotenv(ENV_FILE)

    url = os.getenv("SUPABASE_URL", "").strip()
    anon_key = os.getenv("SUPABASE_KEY", "").strip()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not url:
        print("[ОШИБКА] SUPABASE_URL не задан в .env")
        sys.exit(1)
    if not service_key:
        print("[ОШИБКА] SUPABASE_SERVICE_ROLE_KEY не задан в .env")
        sys.exit(1)

    return url, anon_key, service_key


def mask_key(key: str) -> str:
    """Маскирует ключ для безопасного вывода (первые 12 + ...)."""
    if len(key) <= 16:
        return key[:6] + "****"
    return key[:12] + "..." + key[-4:]


def make_headers(api_key: str, prefer: Optional[str] = None) -> Dict[str, str]:
    """Создаёт базовые заголовки для запросов к Supabase REST API."""
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


# ---------------------------------------------------------------------------
# Подход 1: Supabase Python client (если установлен)
# ---------------------------------------------------------------------------


def try_supabase_client(url: str, service_key: str) -> Optional[Dict[str, Any]]:
    """
    Пытается использовать supabase-py клиент для выполнения SQL через RPC.
    Возвращает собранную схему или None при неудаче.
    """
    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        print("[ПОДХОД 1] supabase-py не установлен, пропускаем.")
        return None

    try:
        client = create_client(url, service_key)
    except Exception as exc:
        print(f"[ПОДХОД 1] Не удалось создать supabase-клиент: {exc}")
        return None

    # Проверяем наличие RPC-функции для выполнения SQL
    rpc_name = None
    for name in RPC_EXEC_SQL_NAMES:
        try:
            # Пробуем вызвать с простым тестовым запросом
            test_result = client.rpc(name, {"sql_query": "SELECT 1 AS test"}).execute()
            rpc_name = name
            print(f"[ПОДХОД 1] Найдена RPC-функция '{rpc_name}', выполняем SQL-запросы...")
            break
        except Exception:
            continue

    if rpc_name is None:
        print("[ПОДХОД 1] RPC-функция exec_sql не найдена в БД.")
        print("  Чтобы включить этот подход, создайте в Supabase SQL Editor функцию:")
        print("  CREATE OR REPLACE FUNCTION exec_sql(sql_query text)")
        print("  RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER")
        print("  AS $$ DECLARE result JSONB; BEGIN")
        print("    EXECUTE 'SELECT jsonb_agg(t) FROM (' || sql_query || ') t' INTO result;")
        print("    RETURN result;")
        print("  END; $$;")
        return None

    # Выполняем все запросы через RPC
    schema: Dict[str, Any] = {}
    for section, sql in QUERIES.items():
        try:
            resp = client.rpc(rpc_name, {"sql_query": sql.strip()}).execute()
            schema[section] = resp.data if resp.data else []
            print(f"  [OK] {section}: получено {len(schema[section])} записей")
        except Exception as exc:
            print(f"  [ОШИБКА] {section}: {exc}")
            schema[section] = []
            schema.setdefault("_errors", {})[section] = str(exc)

    return schema


# ---------------------------------------------------------------------------
# Подход 2: Прямые HTTP-запросы к Supabase REST API
# ---------------------------------------------------------------------------


def try_rest_api_direct(url: str, service_key: str) -> Optional[Dict[str, Any]]:
    """
    Пытается получить метаданные через прямые запросы к PostgREST.
    Использует несколько стратегий:
      a) OpenAPI-спеку для получения списка таблиц и колонок
      b) Прямые запросы к information_schema через /rest/v1/ (если доступно)
      c) RPC-вызов functions
    """
    schema: Dict[str, Any] = {}
    headers = make_headers(service_key)
    rest_url = url.rstrip("/") + "/rest/v1"

    print("[ПОДХОД 2] Пробуем прямые HTTP-запросы к PostgREST...")

    # --- Стратегия A: OpenAPI-спека для таблиц/колонок ---
    print("  Стратегия A: получение OpenAPI-спеки для таблиц и колонок...")
    try:
        openapi_headers = make_headers(service_key)
        openapi_headers["Accept"] = "application/openapi+json"
        resp = requests.get(rest_url + "/", headers=openapi_headers, timeout=30)

        if resp.status_code == 200 and "paths" in resp.json():
            openapi = resp.json()
            tables_data = _parse_openapi_tables(openapi)
            if tables_data:
                schema["tables_and_columns_from_openapi"] = tables_data
                schema["_notes"] = (
                    "Колонки получены из OpenAPI-спеки PostgREST. "
                    "Типы данных и ограничения не включены — используйте SQL для полной информации."
                )
                print(f"    [OK] Найдено {len(tables_data)} таблиц через OpenAPI")
            else:
                print("    [~] OpenAPI-спека получена, но таблицы не найдены")
        else:
            print(f"    [~] OpenAPI-спека недоступна (HTTP {resp.status_code})")
    except Exception as exc:
        print(f"    [ОШИБКА] OpenAPI: {exc}")

    # --- Стратегия B: Список таблиц через GET /rest/v1/ ---
    print("  Стратегия B: получение списка таблиц через GET /rest/v1/ ...")
    try:
        resp = requests.get(
            rest_url + "/",
            headers={**headers, "Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "definitions" in data:
                # Старый формат OpenAPI
                tables = list(data.get("definitions", {}).keys())
                if tables:
                    schema["_table_names_from_rest"] = tables
                    print(f"    [OK] Получено {len(tables)} определений таблиц")
            elif isinstance(data, dict):
                print(f"    [~] Ответ получен, ключи: {list(data.keys())[:10]}")
            else:
                print(f"    [~] Неожиданный формат ответа (тип: {type(data).__name__})")
        else:
            print(f"    [~] GET /rest/v1/ вернул HTTP {resp.status_code}")
    except Exception as exc:
        print(f"    [ОШИБКА] GET /rest/v1/: {exc}")

    # --- Стратегия C: Попытка RPC через HTTP POST ---
    print("  Стратегия C: попытка вызова RPC через HTTP POST ...")
    got_any_rpc = False
    for rpc_name in RPC_EXEC_SQL_NAMES:
        if got_any_rpc:
            break
        for section, sql in QUERIES.items():
            try:
                rpc_headers = make_headers(service_key, prefer="return=representation")
                resp = requests.post(
                    f"{rest_url}/rpc/{rpc_name}",
                    headers=rpc_headers,
                    json={"sql_query": sql.strip()},
                    timeout=60,
                )
                if resp.status_code == 200:
                    schema.setdefault(section, resp.json() if resp.text else [])
                    print(f"    [OK] {section} через RPC '{rpc_name}': {len(schema[section])} записей")
                    got_any_rpc = True
                elif resp.status_code == 404:
                    # Функция не найдена, пробуем следующую
                    break
                else:
                    print(f"    [~] RPC '{rpc_name}' → {section}: HTTP {resp.status_code} — {resp.text[:100]}")
            except Exception as exc:
                print(f"    [ОШИБКА] RPC '{rpc_name}' → {section}: {exc}")

    if got_any_rpc:
        print("  [OK] Подход 2 (RPC через HTTP) успешен для некоторых секций")

    if not schema or all(k.startswith("_") for k in schema):
        print("[ПОДХОД 2] Не удалось получить метаданные через REST API.")
        return None

    return schema


def _parse_openapi_tables(openapi: dict) -> List[Dict[str, Any]]:
    """Извлекает список таблиц и их колонок из OpenAPI-спеки PostgREST."""
    tables: List[Dict[str, Any]] = []
    paths = openapi.get("paths", {})

    for path, methods in paths.items():
        # Пути вида /table_name
        table_name = path.strip("/")
        if not table_name or table_name.startswith("rpc/"):
            continue

        get_method = methods.get("get", {})
        parameters = get_method.get("parameters", [])

        columns = []
        for param in parameters:
            if param.get("in") == "query" and param.get("name"):
                col_name = param["name"]
                # Исключаем специальные параметры PostgREST
                if col_name not in ("select", "order", "limit", "offset", "or", "and", "on_conflict"):
                    columns.append({"column_name": col_name})

        if columns:
            tables.append({"table_name": table_name, "columns": columns})

    return tables


# ---------------------------------------------------------------------------
# Подход 3: Fallback — генерация SQL и шаблона JSON
# ---------------------------------------------------------------------------


def generate_fallback(url: str, anon_key: str, service_key: str) -> Dict[str, Any]:
    """
    Генерирует SQL-файл для ручного выполнения и создаёт шаблон JSON.
    Возвращает шаблонную структуру схемы.
    """
    print("\n[ПОДХОД 3] Генерация fallback: SQL-запросы и шаблон JSON...")

    # Собираем все SQL-запросы в один файл
    sql_lines = [
        "-- ============================================================",
        "-- SQL-запросы для получения метаданных из Supabase",
        "-- Скопируйте и выполните их в Supabase SQL Editor",
        "-- (https://supabase.com/dashboard/project/_/sql)",
        "-- ============================================================",
        "",
    ]

    for section, sql in QUERIES.items():
        sql_lines.append(f"-- Секция: {section}")
        sql_lines.append("-- " + "-" * 50)
        sql_lines.append(sql.strip())
        sql_lines.append("")
        sql_lines.append("")

    sql_text = "\n".join(sql_lines)

    try:
        FALLBACK_SQL_FILE.write_text(sql_text, encoding="utf-8")
        print(f"  [OK] SQL-запросы сохранены в: {FALLBACK_SQL_FILE}")
    except Exception as exc:
        print(f"  [ОШИБКА] Не удалось записать SQL-файл: {exc}")

    # Создаём шаблон JSON
    template: Dict[str, Any] = {
        "_instructions": {
            "title": "ШАБЛОН — данные не получены автоматически",
            "steps": [
                "1. Откройте Supabase SQL Editor: https://supabase.com/dashboard/project/_/sql",
                f"2. Выполните запросы из файла: {FALLBACK_SQL_FILE.name}",
                "3. Скопируйте результаты в соответствующие секции этого JSON",
                "4. Или создайте RPC-функцию exec_sql для автоматического сбора (см. вывод скрипта)",
            ],
            "supabase_url": url,
            "anon_key_masked": mask_key(anon_key) if anon_key else "не задан",
            "service_key_masked": mask_key(service_key),
        },
        "tables": [],
        "rls_status": [],
        "rls_policies": [],
        "indexes": [],
        "enums": [],
        "_queries": {section: sql.strip() for section, sql in QUERIES.items()},
    }

    print(f"  [OK] Создан шаблон JSON с инструкциями и SQL-запросами")
    print(f"\n{'='*60}")
    print(f"Чтобы автоматический сбор работал, создайте в БД RPC-функцию:")
    print(f"  Откройте SQL Editor и выполните:")
    print(f"")
    print(f"  CREATE OR REPLACE FUNCTION exec_sql(sql_query text)")
    print(f"  RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER")
    print(f"  AS $$")
    print(f"  DECLARE result JSONB;")
    print(f"  BEGIN")
    print(f"    EXECUTE 'SELECT jsonb_agg(t) FROM (' || sql_query || ') t' INTO result;")
    print(f"    RETURN coalesce(result, '[]'::jsonb);")
    print(f"  END;")
    print(f"  $$;")
    print(f"{'='*60}")

    return template


# ---------------------------------------------------------------------------
# Основная логика
# ---------------------------------------------------------------------------


def collect_schema() -> Dict[str, Any]:
    """Собирает схему БД, пробуя все доступные подходы."""
    url, anon_key, service_key = load_env()

    print(f"Supabase URL : {url}")
    print(f"Anon key    : {mask_key(anon_key) if anon_key else 'не задан'}")
    print(f"Service key : {mask_key(service_key)}")
    print()

    schema: Optional[Dict[str, Any]] = None

    # Подход 1: supabase-py клиент
    schema = try_supabase_client(url, service_key)
    if schema:
        print("\n[УСПЕХ] Подход 1 (supabase-py) сработал!")
        schema["_collection_method"] = "supabase-py RPC"
        return schema

    # Подход 2: прямые HTTP-запросы
    print()
    schema = try_rest_api_direct(url, service_key)
    if schema and any(not k.startswith("_") for k in schema):
        print("\n[УСПЕХ] Подход 2 (REST API) сработал частично!")
        schema["_collection_method"] = "REST API direct"
        return schema

    # Подход 3: fallback
    print()
    schema = generate_fallback(url, anon_key, service_key)
    schema["_collection_method"] = "fallback (шаблон)"
    return schema


def build_final_schema(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Приводит сырые данные к единому формату выходного JSON.
    """
    final: Dict[str, Any] = {
        "_meta": {
            "generated_by": "dump_supabase_schema.py",
            "collection_method": raw.get("_collection_method", "unknown"),
            "notes": raw.get("_notes", ""),
            "instructions": raw.get("_instructions", None),
            "queries": raw.get("_queries", None),
            "errors": raw.get("_errors", None),
        },
        "tables": raw.get("tables", []),
        "rls_status": raw.get("rls_status", []),
        "rls_policies": raw.get("rls_policies", []),
        "indexes": raw.get("indexes", []),
        "enums": raw.get("enums", []),
    }

    # Если данные пришли из OpenAPI, добавляем в соответствующую секцию
    openapi_tables = raw.get("tables_and_columns_from_openapi")
    if openapi_tables and not final["tables"]:
        final["tables"] = openapi_tables

    # Если есть только имена таблиц из REST, добавляем их
    rest_table_names = raw.get("_table_names_from_rest")
    if rest_table_names and not final["tables"]:
        final["tables"] = [{"table_name": name, "columns": []} for name in rest_table_names]

    # Убираем внутренние ключи
    final["_meta"].pop("instructions", None)
    final["_meta"].pop("queries", None)
    final["_meta"].pop("errors", None)
    if raw.get("_instructions") is not None:
        final["_meta"]["instructions"] = raw["_instructions"]
    if raw.get("_queries") is not None:
        final["_meta"]["queries"] = raw["_queries"]
    if raw.get("_errors") is not None:
        final["_meta"]["errors"] = raw["_errors"]

    return final


def main() -> None:
    """Точка входа."""
    print("=" * 60)
    print("  Supabase Schema Dumper для проекта «Трудник»")
    print("=" * 60)
    print()

    try:
        raw_schema = collect_schema()
    except Exception as exc:
        print(f"\n[КРИТИЧЕСКАЯ ОШИБКА] {exc}")
        sys.exit(1)

    final_schema = build_final_schema(raw_schema)

    # Запись результата
    try:
        json_text = json.dumps(final_schema, ensure_ascii=False, indent=2, default=str)
        OUTPUT_FILE.write_text(json_text, encoding="utf-8")
        print(f"\n[ГОТОВО] Схема сохранена в: {OUTPUT_FILE}")
        print(f"  Размер: {OUTPUT_FILE.stat().st_size:,} байт")
    except Exception as exc:
        print(f"\n[ОШИБКА] Не удалось записать {OUTPUT_FILE}: {exc}")
        sys.exit(1)

    # Краткая статистика
    print(f"\n  Секции:")
    for section in ["tables", "rls_status", "rls_policies", "indexes", "enums"]:
        count = len(final_schema.get(section, []))
        print(f"    {section}: {count} записей")


if __name__ == "__main__":
    main()
