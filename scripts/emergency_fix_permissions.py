#!/usr/bin/env python3
"""EMERGENCY: Fix database permissions. CLI-only."""
import os
import sys

if '--confirm-i-know-what-i-do' not in sys.argv:
    print('ERROR: Add --confirm-i-know-what-i-do to confirm.')
    sys.exit(1)

import psycopg2

db_url = os.environ.get('DATABASE_URL') or os.environ.get('PGDATABASE_URL', '')
if not db_url:
    pg_user = os.environ.get('PGUSER', '')
    pg_password = os.environ.get('PGPASSWORD', '')
    pg_host = os.environ.get('PGHOST', '')
    pg_port = os.environ.get('PGPORT', '5432')
    pg_database = os.environ.get('PGDATABASE', '')
    if all([pg_user, pg_password, pg_host, pg_database]):
        db_url = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
    else:
        print('DATABASE_URL not configured')
        sys.exit(1)

conn = psycopg2.connect(db_url)
conn.autocommit = True
try:
    with conn.cursor() as cur:
        cur.execute("""
            DO $$
            DECLARE r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', r.tablename);
                END LOOP;
            END $$;

            GRANT anon, authenticated, service_role TO trudnik;
            GRANT anon, authenticated, service_role TO trudnikapp;
            GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
            GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
            GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
            GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO service_role;
        """)
        print('Permissions fixed successfully.')
finally:
    conn.close()
