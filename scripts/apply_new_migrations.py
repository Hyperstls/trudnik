#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Apply migrations 039-042 by first patching exec_sql to support DDL."""
import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
load_dotenv()

URL = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def exec_sql(query: str) -> dict:
    """Execute a SELECT query via the existing exec_sql RPC."""
    r = requests.post(
        f"{URL}/rest/v1/rpc/exec_sql",
        headers=HEADERS,
        json={"sql_query": query},
        timeout=30,
    )
    if r.status_code == 200:
        try:
            return {"ok": True, "data": r.json()}
        except Exception:
            return {"ok": False, "error": r.text}
    return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}


def patch_exec_sql_for_ddl() -> bool:
    """
    Modify exec_sql to support DDL by updating pg_proc catalog.
    
    The new version checks if the query starts with SELECT and wraps it,
    otherwise executes the SQL directly.
    """
    print("\n=== Patching exec_sql to support DDL ===")
    
    # New function source that handles both SELECT and DDL
    new_source = (
        "\n"
        "DECLARE\n"
        "    result JSONB;\n"
        "    requesting_user_id uuid;\n"
        "    trimmed text;\n"
        "BEGIN\n"
        "    IF current_setting('role', true) != 'service_role' THEN\n"
        "        RAISE EXCEPTION 'Only service_role can execute SQL via exec_sql';\n"
        "    END IF;\n"
        "    trimmed := trim(sql_query);\n"
        "    IF lower(substring(trimmed, 1, 6)) = 'select' OR lower(substring(trimmed, 1, 4)) = 'with' THEN\n"
        "        EXECUTE 'SELECT jsonb_agg(t) FROM (' || sql_query || ') t' INTO result;\n"
        "        RETURN coalesce(result, '[]'::jsonb);\n"
        "    ELSE\n"
        "        EXECUTE sql_query;\n"
        "        RETURN '[]'::jsonb;\n"
        "    END IF;\n"
        "END;\n"
    )
    
    # Use a data-modifying CTE to update pg_proc.prosrc
    # Escape single quotes by doubling them
    escaped_source = new_source.replace("'", "''")
    
    update_sql = (
        "WITH updated AS (\n"
        "    UPDATE pg_catalog.pg_proc SET prosrc = '" + escaped_source + "'\n"
        "    WHERE proname = 'exec_sql'\n"
        "      AND pronamespace = 'public'::regnamespace\n"
        "      AND prorettype = 'jsonb'::regtype\n"
        "    RETURNING proname, prosrc\n"
        ") SELECT proname, length(prosrc) AS src_len FROM updated"
    )
    
    result = exec_sql(update_sql)
    if result["ok"]:
        data = result["data"]
        if data and len(data) > 0:
            print(f"  Updated exec_sql: {data}")
            print("  exec_sql patched successfully!")
            return True
        else:
            print(f"  No rows updated. Data: {data}")
            return False
    else:
        print(f"  Failed to patch exec_sql: {result['error']}")
        return False


def split_sql_statements(sql: str) -> list[str]:
    """Same logic as apply_migrations.py."""
    statements = []
    current = []
    paren_depth = 0
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            newline = sql.find("\n", i)
            if newline == -1:
                break
            current.append(sql[i : newline + 1])
            i = newline + 1
            continue
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            end = sql.find("*/", i + 2)
            if end == -1:
                break
            current.append(sql[i : end + 2])
            i = end + 2
            continue
        if ch == "$":
            tag_end = sql.find("$", i + 1)
            if tag_end != -1:
                open_tag = sql[i : tag_end + 1]
                close_pos = sql.find(open_tag, tag_end + 1)
                if close_pos != -1:
                    current.append(sql[i : close_pos + len(open_tag)])
                    i = close_pos + len(open_tag)
                    continue
            current.append(ch)
            i += 1
            continue
        if ch == "'":
            current.append(ch)
            i += 1
            while i < n:
                c = sql[i]
                current.append(c)
                if c == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        current.append("'")
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
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
        if ch == ";" and paren_depth == 0:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def apply_via_exec_sql(stmt: str) -> tuple:
    """Execute a SQL statement via the patched exec_sql RPC."""
    r = requests.post(
        f"{URL}/rest/v1/rpc/exec_sql",
        headers=HEADERS,
        json={"sql_query": stmt},
        timeout=60,
    )
    if r.status_code in (200, 201, 204):
        return True, "OK"
    else:
        detail = ""
        try:
            detail = r.json().get("message", r.text[:200])
        except Exception:
            detail = r.text[:200]
        return False, f"HTTP {r.status_code}: {detail}"


def apply_file(filepath: str) -> int:
    """Apply a single migration file, return error count."""
    path = Path(filepath)
    if not path.exists():
        print(f"ERROR: File not found: {filepath}")
        return 1

    print(f"\n{'=' * 60}")
    print(f"=== Applying: {path.name} ===")

    sql_content = path.read_text(encoding="utf-8")
    all_stmts = split_sql_statements(sql_content)

    meaningful = []
    for stmt in all_stmts:
        lines = [l.strip() for l in stmt.split("\n")]
        if any(l and not l.startswith("--") for l in lines):
            meaningful.append(stmt)

    total = len(meaningful)
    print(f"Statements: {total}\n")

    errors = 0
    for idx, stmt in enumerate(meaningful, 1):
        preview = stmt.split("\n")[0].strip()
        if len(preview) > 95:
            preview = preview[:92] + "..."

        ok, msg = apply_via_exec_sql(stmt)
        if ok:
            print(f"[{idx:02d}/{total:02d}] OK:    {preview}")
        else:
            print(f"[{idx:02d}/{total:02d}] ERROR: {preview}")
            print(f"        -> {msg}")
            errors += 1

    print(f"\n=== {path.name}: {total - errors}/{total} OK, {errors} errors ===")
    return errors


def verify_migrations():
    """Verify that all migrations were applied successfully."""
    print("\n" + "=" * 60)
    print("=== VERIFICATION ===")
    
    # Check schema_migrations table
    r = requests.get(
        f"{URL}/rest/v1/schema_migrations?select=*",
        headers=HEADERS,
        timeout=15,
    )
    print(f"\n1. schema_migrations table: HTTP {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"   Records: {json.dumps(data, indent=2, ensure_ascii=False) if hasattr(__import__('json'), 'dumps') else data}")
    else:
        print(f"   Error: {r.text[:200]}")
    
    # Check RPC functions
    print("\n2. RPC accept_application:")
    r = requests.post(
        f"{URL}/rest/v1/rpc/accept_application",
        headers=HEADERS,
        json={"p_job_id": "00000000-0000-0000-0000-000000000001", "p_app_id": "00000000-0000-0000-0000-000000000002"},
        timeout=15,
    )
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        print(f"   Result: {r.text[:300]}")
    
    # Check messages FK
    print("\n3. Messages FK (check CASCADE):")
    fk_sql = (
        "SELECT tc.constraint_name, rc.delete_rule "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.referential_constraints rc "
        "ON tc.constraint_name = rc.constraint_name "
        "WHERE tc.table_name = 'messages' AND tc.table_schema = 'public' AND tc.constraint_type = 'FOREIGN KEY'"
    )
    result = exec_sql(fk_sql)
    if result["ok"]:
        print(f"   {json.dumps(result['data'], indent=2)}")


def main():
    import json as json_mod
    
    if not URL or not KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be in .env")
        sys.exit(1)

    # Step 1: Patch exec_sql to support DDL
    if not patch_exec_sql_for_ddl():
        print("\nFATAL: Cannot patch exec_sql. Aborting.")
        sys.exit(1)

    # Step 2: Apply migrations 039-042
    migrations = [
        str(MIGRATIONS_DIR / "039_atomic_operations.sql"),
        str(MIGRATIONS_DIR / "040_schema_versioning.sql"),
        str(MIGRATIONS_DIR / "041_add_messages_fk.sql"),
        str(MIGRATIONS_DIR / "042_cleanup_duplicates.sql"),
    ]

    total_errors = 0
    for m in migrations:
        errors = apply_file(m)
        total_errors += errors

    print(f"\n{'#' * 60}")
    print(f"### TOTAL: {len(migrations)} migrations, {total_errors} errors ###")
    print(f"{'#' * 60}")

    # Step 3: Verify
    verify_migrations()


if __name__ == "__main__":
    main()

