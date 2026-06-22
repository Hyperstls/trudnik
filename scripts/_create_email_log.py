#!/usr/bin/env python
"""Create email_log table."""
import os
import psycopg2

DB_URL = os.environ.get('DATABASE_URL')
assert DB_URL, "DATABASE_URL environment variable must be set"

SQL = """
CREATE TABLE IF NOT EXISTS public.email_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    notification_id BIGINT REFERENCES notifications(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    error TEXT,
    to_email TEXT,
    subject TEXT,
    template_name VARCHAR(100),
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

conn = psycopg2.connect(DB_URL)
conn.autocommit = True
cur = conn.cursor()
cur.execute(SQL)
conn.close()
print("email_log table created")
