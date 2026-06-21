#!/usr/bin/env python
"""Create base tables needed by migrations."""
import os
import psycopg2

DB_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:postgres@127.0.0.1:54322/postgres'
)

SQL = """
CREATE TABLE IF NOT EXISTS public.profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role text DEFAULT 'worker',
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);
"""

conn = psycopg2.connect(DB_URL)
conn.autocommit = True
cur = conn.cursor()
cur.execute(SQL)
conn.close()
print("profiles table created")
