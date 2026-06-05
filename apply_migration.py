# -*- coding: utf-8 -*-
"""
Скрипт для применения SQL-миграции напрямую через Supabase REST API.
Использует сервисный ключ (SUPABASE_SERVICE_ROLE_KEY) для выполнения DDL.
"""
import io
import os
import sys
import requests
from dotenv import load_dotenv

# Принудительная UTF-8 для вывода
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json"
}

def split_sql_statements(sql: str) -> list[str]:
    """Разделяет SQL-текст на отдельные выражения по ';'."""
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
    stmt = ''.join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements

def execute_sql_statement(sql: str) -> tuple[bool, str]:
    """Выполняет один SQL-запрос через REST API Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/execute_sql"
    try:
        resp = requests.post(url, headers=HEADERS, json={"sql": sql}, timeout=60)
        if resp.status_code in (200, 201, 204):
            return True, resp.text[:200] if resp.text else "OK"
        else:
            return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
    except requests.Timeout:
        return False, "Timeout"
    except requests.RequestException as e:
        return False, str(e)

def main():
    migration_file = "migrations/006_add_monetization.sql"
    
    if not os.path.exists(migration_file):
        print(f"ERROR: Migration file not found: {migration_file}")
        sys.exit(1)
    
    with open(migration_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    print(f"Loaded migration: {migration_file} ({len(sql_content)} chars)")
    
    statements = split_sql_statements(sql_content)
    print(f"Found {len(statements)} SQL statements\n")
    
    success_count = 0
    error_count = 0
    
    for i, stmt in enumerate(statements, 1):
        stmt = stmt.strip()
        if not stmt:
            continue
        
        # Пропускаем комментарии
        if stmt.startswith('--'):
            continue
        
        preview = stmt[:80] + ('...' if len(stmt) > 80 else '')
        print(f"[{i}/{len(statements)}] >> {preview}")
        
        ok, msg = execute_sql_statement(stmt)
        if ok:
            print(f"  OK: {msg[:100]}")
            success_count += 1
        else:
            print(f"  ERROR: {msg[:200]}")
            error_count += 1
    
    print("\n" + "="*50)
    print(f"Success: {success_count}")
    print(f"Errors: {error_count}")
    
    if error_count > 0:
        print("\nWARNING: Some commands failed.")
        print("Tables/columns may already exist (IF NOT EXISTS).")
        print("Check Supabase Dashboard -> SQL Editor -> run manually if needed.")
        sys.exit(1)
    else:
        print("\nMigration applied successfully!")

if __name__ == "__main__":
    main()
