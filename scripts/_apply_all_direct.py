#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Apply ALL migrations directly via psycopg2 to Supabase PostgreSQL."""
import io
import os
import re
import sys
from pathlib import Path

import psycopg2

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DB_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:postgres@127.0.0.1:54322/postgres'
)
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL text into individual statements by ';'."""
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


def preview(stmt: str, max_len: int = 95) -> str:
    for line in stmt.split("\n"):
        s = line.strip()
        if s and not s.startswith("--"):
            if len(s) > max_len:
                return s[:max_len - 3] + "..."
            return s
    return stmt[:max_len]


def apply_file(conn, filepath: Path) -> int:
    print(f"\n{'=' * 60}")
    print(f"=== {filepath.name} ===")

    sql_content = filepath.read_text(encoding="utf-8")
    all_stmts = split_sql_statements(sql_content)

    meaningful = []
    for stmt in all_stmts:
        lines = [l.strip() for l in stmt.split("\n")]
        if any(l and not l.startswith("--") for l in lines):
            meaningful.append(stmt)

    total = len(meaningful)
    print(f"Statements: {total}")

    errors = 0
    cur = conn.cursor()

    for idx, stmt in enumerate(meaningful, 1):
        p = preview(stmt)
        try:
            cur.execute(stmt)
            print(f"[{idx:02d}/{total:02d}] OK:    {p}")
        except Exception as e:
            # Extract meaningful error
            err_msg = str(e).strip()
            if "\n" in err_msg:
                err_msg = err_msg.split("\n")[0]
            print(f"[{idx:02d}/{total:02d}] ERROR: {p}")
            print(f"        -> {err_msg[:200]}")
            errors += 1
            conn.rollback()
            # Re-create cursor after rollback
            cur = conn.cursor()

    cur.close()
    print(f"=== {filepath.name}: {total - errors}/{total} OK, {errors} errors ===")
    return errors


def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True

    files = sorted(
        f for f in MIGRATIONS_DIR.glob("*.sql")
        if re.match(r"^\d{3}_", f.name)
    )

    total_files = len(files)
    total_errors = 0

    print(f"\n{'#' * 60}")
    print(f"### DIRECT PSYCOPG2: {total_files} migrations ###")
    print(f"{'#' * 60}")

    for idx, f in enumerate(files, 1):
        print(f"\n--- Migration {idx}/{total_files}: {f.name} ---")
        errs = apply_file(conn, f)
        total_errors += errs

    conn.close()

    print(f"\n{'#' * 60}")
    print(f"### TOTAL: {total_files} migrations, {total_errors} errors ###")
    print(f"{'#' * 60}")

    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
