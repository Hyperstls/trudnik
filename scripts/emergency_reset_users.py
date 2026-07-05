#!/usr/bin/env python3
"""EMERGENCY: Reset all users. CLI-only. Use with extreme caution."""
import os
import sys

if '--confirm-i-know-what-i-do' not in sys.argv:
    print('ERROR: This script resets ALL users. Add --confirm-i-know-what-i-do to confirm.')
    print('Usage: python scripts/emergency_reset_users.py --confirm-i-know-what-i-do')
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
        print('WARNING: This will delete ALL users and their data.')
        print('Proceeding in 5 seconds... (Ctrl+C to abort)')
        import time
        time.sleep(5)

        # Сохранить admin-пользователей
        cur.execute("""
            DELETE FROM notifications CASCADE;
            DELETE FROM applications CASCADE;
            DELETE FROM favorites CASCADE;
            DELETE FROM blacklists CASCADE;
            DELETE FROM ratings CASCADE;
            DELETE FROM invitations CASCADE;
            DELETE FROM messages CASCADE;
            DELETE FROM push_subscriptions CASCADE;
            DELETE FROM user_skills CASCADE;
            DELETE FROM jobs CASCADE;
            DELETE FROM profiles WHERE role != 'admin';
        """)
        print('All non-admin users and their data have been deleted.')
finally:
    conn.close()
