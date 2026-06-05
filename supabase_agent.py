"""
AI-агент для управления Supabase через естественный язык (DeepSeek + Supabase REST API).

ВНИМАНИЕ: Для выполнения произвольных SQL-запросов через REST API Supabase требуется
создать в базе данных PL/pgSQL-функцию execute_sql:

    CREATE OR REPLACE FUNCTION execute_sql(sql text)
    RETURNS SETOF jsonb
    LANGUAGE plpgsql
    SECURITY DEFINER
    AS $$
    BEGIN
        RETURN QUERY EXECUTE sql;
    END;
    $$;

Без этой функции все SQL-запросы будут возвращать ошибку 404.
"""

import os
import sys
from openai import OpenAI
import requests

# Загружаем переменные окружения из .env (если используется python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# --- SQL-безопасность: недопустимые операции ---
DESTRUCTIVE_KEYWORDS = [
    "DROP TABLE", "DROP DATABASE", "DROP SCHEMA", "DROP VIEW", "DROP FUNCTION",
    "TRUNCATE", "ALTER TABLE", "ALTER DATABASE", "ALTER SCHEMA",
    "CREATE TABLE", "CREATE DATABASE", "CREATE SCHEMA",
    "REINDEX", "CLUSTER", "VACUUM", "REASSIGN", "REVOKE",
    "GRANT ALL", "GRANT ALL PRIVILEGES",
]


def _require_env(name: str) -> str:
    """Получить значение переменной окружения или завершить с ошибкой."""
    value = os.getenv(name)
    if not value:
        print(f"Ошибка: не задана переменная окружения {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _init_client():
    """Инициализировать OpenAI-клиент для DeepSeek."""
    api_key = _require_env("DEEPSEEK_API_KEY")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com/v1"
    )


def _init_headers():
    """Инициализировать HTTP-заголовки для Supabase REST API."""
    supabase_url = _require_env("SUPABASE_URL")
    service_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json"
    }
    return supabase_url, headers


def validate_sql_safe(sql: str) -> tuple[bool, str]:
    """Проверяет SQL на наличие деструктивных операций. Возвращает (OK, сообщение)."""
    sql_upper = sql.upper().strip()
    for kw in DESTRUCTIVE_KEYWORDS:
        if kw.upper() in sql_upper:
            return False, f"Запрещённая операция: '{kw}'"
    return True, ""


# --- Функции ---

def get_db_schema(supabase_url: str, headers: dict):
    """Получить список таблиц и политик для контекста."""
    tables = []
    policies = []

    # Запрос к information_schema для списка таблиц
    try:
        sql = """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """
        resp = requests.post(
            f"{supabase_url}/rest/v1/rpc/execute_sql",
            headers=headers,
            json={"sql": sql},
            timeout=30
        )
        if resp.ok:
            data = resp.json()
            tables = [row['table_name'] for row in data] if isinstance(data, list) else []
    except Exception as e:
        print(f"⚠ Предупреждение: не удалось получить список таблиц: {e}", file=sys.stderr)

    # Политики (упрощённо – через отдельный запрос)
    try:
        policies_sql = """
        SELECT policyname, tablename FROM pg_policies WHERE schemaname = 'public';
        """
        resp = requests.post(
            f"{supabase_url}/rest/v1/rpc/execute_sql",
            headers=headers,
            json={"sql": policies_sql},
            timeout=30
        )
        if resp.ok:
            data = resp.json()
            policies = [f"{row['policyname']} on {row['tablename']}" for row in data]
    except Exception as e:
        print(f"⚠ Предупреждение: не удалось получить список политик: {e}", file=sys.stderr)

    return {
        "tables": tables,
        "policies": policies
    }


def execute_sql(supabase_url: str, headers: dict, sql: str) -> tuple[bool, str]:
    """Выполнить произвольный SQL-запрос через REST API Supabase."""
    ok, msg = validate_sql_safe(sql)
    if not ok:
        return False, msg

    url = f"{supabase_url}/rest/v1/rpc/execute_sql"
    try:
        resp = requests.post(url, headers=headers, json={"sql": sql}, timeout=30)
        if resp.status_code in (200, 201, 204):
            return True, resp.text[:200]
        else:
            return False, resp.text[:200]
    except requests.Timeout:
        return False, "Таймаут запроса к Supabase"
    except requests.RequestException as e:
        return False, str(e)


def run_command(command: str, client: OpenAI, supabase_url: str, headers: dict,
                dry_run: bool = False, confirm: bool = True):
    """Основная логика: получить SQL от DeepSeek и выполнить его."""
    schema = get_db_schema(supabase_url, headers)

    tables_str = ', '.join(schema['tables']) if schema['tables'] else '(не удалось получить)'
    policies_str = ', '.join(schema['policies']) if schema['policies'] else 'нет'

    prompt = f"""
Ты — эксперт по Supabase и PostgreSQL. У тебя есть доступ к базе данных со следующими таблицами: {tables_str}.
Активные политики: {policies_str}.

Пользователь дал команду: "{command}"

Напиши SQL-запрос, который нужно выполнить. Если команда не требует SQL (например, просто вопрос о схеме), ответь "none".
Верни ТОЛЬКО SQL-запрос без пояснений. Если запросов несколько, раздели их точкой с запятой.
ВНИМАНИЕ: запрещены деструктивные операции: DROP, TRUNCATE, ALTER, CREATE TABLE, а также GRANT ALL PRIVILEGES.
"""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=500
    )
    sql = response.choices[0].message.content.strip()

    # Очищаем возможные обёртки Markdown
    if sql.startswith("```sql"):
        sql = sql[6:]
    elif sql.startswith("```"):
        sql = sql[3:]
    if sql.endswith("```"):
        sql = sql[:-3]
    sql = sql.strip()

    if not sql or sql.lower() == "none":
        print("ℹ Команда не требует SQL.")
        return

    # Разделяем на отдельные SQL-команды (базовый подход)
    statements = _split_sql_statements(sql)

    print(f"\n🧪 Сгенерированный SQL ({len(statements)} команд):")
    for i, stmt in enumerate(statements, 1):
        print(f"  [{i}] {stmt}")

    if dry_run:
        print("\n🔍 Режим dry-run: SQL не выполнялся.")
        return

    if confirm:
        answer = input("\n❓ Выполнить эти SQL-команды? (y/N): ").strip().lower()
        if answer not in ("y", "yes", "д", "да"):
            print("❌ Отменено пользователем.")
            return

    # Выполняем каждую команду
    for i, stmt in enumerate(statements, 1):
        stmt = stmt.strip()
        if not stmt:
            continue
        print(f"\n▶ Выполняю [{i}/{len(statements)}]: {stmt[:80]}...")
        success, message = execute_sql(supabase_url, headers, stmt)
        if success:
            print(f"  ✅ Успешно: {message[:100]}")
        else:
            print(f"  ❌ Ошибка: {message[:200]}")


def _split_sql_statements(sql: str) -> list[str]:
    """Разделяет SQL-текст на отдельные выражения по ';' с базовой защитой от строк."""
    statements = []
    current = []
    in_string = False
    string_char = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_string:
            current.append(ch)
            if ch == string_char and (i == 0 or sql[i-1] != '\\'):
                in_string = False
                string_char = None
        else:
            if ch in ("'", '"'):
                in_string = True
                string_char = ch
                current.append(ch)
            elif ch == ';':
                stmt = ''.join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
            else:
                current.append(ch)
        i += 1
    # Последняя команда (без точки с запятой на конце)
    stmt = ''.join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


# --- CLI ---
if __name__ == "__main__":
    import argparse

    # Инициализация (только при прямом запуске, чтобы не блокировать импорт)
    client = _init_client()
    supabase_url, headers = _init_headers()

    parser = argparse.ArgumentParser(
        description="AI-агент для управления Supabase через естественный язык"
    )
    parser.add_argument("command", nargs="*", help="Команда на естественном языке")
    parser.add_argument("--dry-run", action="store_true",
                        help="Показать сгенерированный SQL без выполнения")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Не запрашивать подтверждение перед выполнением SQL")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    user_cmd = " ".join(args.command)
    run_command(user_cmd, client=client, supabase_url=supabase_url, headers=headers,
                dry_run=args.dry_run, confirm=not args.yes)
