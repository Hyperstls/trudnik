#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create exec_sql RPC function directly in PostgreSQL."""
import os
import sys
import psycopg2

DB_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:postgres@127.0.0.1:54322/postgres'
)

EXEC_SQL_DEFINITION = """
CREATE OR REPLACE FUNCTION public.exec_sql(sql_query text)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    result JSONB;
    trimmed text;
    _query_preview text;
BEGIN
    IF current_setting('role', true) != 'service_role' THEN
        RAISE EXCEPTION 'Only service_role can execute SQL via exec_sql';
    END IF;
    trimmed := trim(sql_query);

    -- Аудит-лог: записываем первые 200 символов запроса в лог PostgreSQL
    _query_preview := left(replace(trimmed, E'\n', ' '), 200);
    RAISE LOG '[exec_sql AUDIT] role=service_role query=%', _query_preview;

    IF lower(substring(trimmed, 1, 6)) = 'select'
       OR lower(substring(trimmed, 1, 4)) = 'with' THEN
        EXECUTE 'SELECT jsonb_agg(t) FROM (' || sql_query || ') t' INTO result;
        RETURN coalesce(result, '[]'::jsonb);
    ELSE
        EXECUTE sql_query;
        RETURN '[]'::jsonb;
    END IF;
END;
$$;
"""

PERMISSIONS_SQL = """
GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;
REVOKE EXECUTE ON FUNCTION public.exec_sql(text) FROM anon, authenticated, PUBLIC;
"""

def main():
    try:
        conn = psycopg2.connect(DB_URL)
        conn.autocommit = True
        cur = conn.cursor()

        print("Creating exec_sql function...")
        cur.execute(EXEC_SQL_DEFINITION)
        print("  -> exec_sql created.")

        print("Setting permissions...")
        cur.execute(PERMISSIONS_SQL)
        print("  -> Permissions set.")

        conn.close()
        print("\nexec_sql is ready.")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
