#!/usr/bin/env python
"""Create notifications and ratings tables without FK to dropped shifts table."""
import os
import psycopg2

DB_URL = os.environ.get('DATABASE_URL')
assert DB_URL, "DATABASE_URL environment variable must be set"

SQL = """
-- ratings (облачная схема: без shift_id, с updated_at)
CREATE TABLE IF NOT EXISTS public.ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rated_user_id UUID NOT NULL,
    rater_user_id UUID NOT NULL,
    rating_type VARCHAR(20) NOT NULL,
    target_type VARCHAR(20) NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- notifications (облачная схема: без title/job_id/shift_id/application_id)
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    type TEXT NOT NULL,
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

conn = psycopg2.connect(DB_URL)
conn.autocommit = True
cur = conn.cursor()
try:
    cur.execute(SQL)
    print("notifications and ratings tables created")
except Exception as e:
    print(f"Error: {e}")
conn.close()
