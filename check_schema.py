#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check current Supabase schema and compare with expectations."""
import io, os, json, sys
from dotenv import load_dotenv
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
load_dotenv()

URL = os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def exec_sql(query):
    r = requests.post(f"{URL}/rest/v1/rpc/exec_sql", headers=H, json={"sql_query": query}, timeout=30)
    if r.status_code == 200:
        return r.json()
    print(f"  SQL ERROR: {r.status_code} {r.text[:300]}")
    return None


def main():
    print("=" * 60)
    print("PUBLIC TABLES")
    print("=" * 60)
    data = exec_sql("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    if data:
        for row in data:
            print(f"  {row['table_name']}")

    print("\n" + "=" * 60)
    print("JOBS STATUS CHECK CONSTRAINT")
    print("=" * 60)
    data = exec_sql("SELECT conname, pg_get_constraintdef(oid) as def FROM pg_constraint WHERE conrelid=(SELECT oid FROM pg_class WHERE relname='jobs' AND relnamespace='public'::regnamespace) AND contype='c'")
    if data:
        for row in data:
            print(f"  {row['conname']}: {row['def']}")

    print("\n" + "=" * 60)
    print("PROFILES COLUMNS (looking for religion duplicates)")
    print("=" * 60)
    data = exec_sql("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='profiles' ORDER BY ordinal_position")
    if data:
        for row in data:
            marker = " <-- DUP?" if row['column_name'] in ('religion', 'religion_id', 'preferred_religion') else ""
            print(f"  {row['column_name']}: {row['data_type']}{marker}")

    print("\n" + "=" * 60)
    print("NOTIFICATIONS COLUMNS (looking for read/is_read duplicates)")
    print("=" * 60)
    data = exec_sql("SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' ORDER BY ordinal_position")
    if data:
        for row in data:
            marker = " <-- DUP?" if row['column_name'] in ('read', 'is_read') else ""
            print(f"  {row['column_name']}: {row['data_type']}{marker}")

    print("\n" + "=" * 60)
    print("MESSAGES FKs (checking delete rules)")
    print("=" * 60)
    data = exec_sql("SELECT tc.constraint_name, kcu.column_name, ccu.table_name AS ref_table, rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name=ccu.constraint_name AND tc.table_schema=ccu.table_schema JOIN information_schema.referential_constraints rc ON tc.constraint_name=rc.constraint_name WHERE tc.table_name='messages' AND tc.table_schema='public' AND tc.constraint_type='FOREIGN KEY'")
    if data:
        for row in data:
            print(f"  {row['constraint_name']}: {row['column_name']} -> {row['ref_table']} ON DELETE {row['delete_rule']}")

    print("\n" + "=" * 60)
    print("RPC FUNCTIONS (checking 039)")
    print("=" * 60)
    data = exec_sql("SELECT proname FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid WHERE n.nspname='public' AND proname IN ('accept_application','reject_application','delete_job_cascade','delete_user_cascade') ORDER BY proname")
    if data:
        for row in data:
            print(f"  FOUND: {row['proname']}")
    else:
        print("  None of the expected RPC functions found!")

    print("\n" + "=" * 60)
    print("SCHEMA MIGRATIONS TABLE")
    print("=" * 60)
    data = exec_sql("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='schema_migrations') AS exists")
    if data:
        print(f"  schema_migrations exists: {data[0]['exists']}")

    print("\n" + "=" * 60)
    print("DEPRECATED TABLES")
    print("=" * 60)
    data = exec_sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('shifts','spatial_ref_sys')")
    if data:
        for row in data:
            print(f"  STILL PRESENT: {row['tablename']}")
    else:
        print("  None found (or already removed)")

    print("\n" + "=" * 60)
    print("SUMMARY: What needs to be done")
    print("=" * 60)
    # Re-check key findings
    rpc_check = exec_sql("SELECT proname FROM pg_proc p JOIN pg_namespace n ON p.pronamespace=n.oid WHERE n.nspname='public' AND proname='accept_application'")
    schema_mig = exec_sql("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='schema_migrations') AS exists")
    
    if not rpc_check:
        print("  [ ] Migration 039: RPC functions NOT created (accept_application, etc.)")
    else:
        print("  [x] Migration 039: RPC functions already exist")
    
    if schema_mig and not schema_mig[0]['exists']:
        print("  [ ] Migration 040: schema_migrations table NOT created")
    else:
        print("  [x] Migration 040: schema_migrations table already exists")
    
    fk_data = exec_sql("SELECT rc.delete_rule FROM information_schema.table_constraints tc JOIN information_schema.referential_constraints rc ON tc.constraint_name=rc.constraint_name WHERE tc.table_name='messages' AND tc.constraint_name='messages_sender_id_fkey'")
    if fk_data and fk_data[0]['delete_rule'] != 'CASCADE':
        print(f"  [ ] Migration 041: messages_sender_id_fkey has ON DELETE {fk_data[0]['delete_rule']} (needs CASCADE)")
    else:
        print("  [x] Migration 041: messages_sender_id_fkey already CASCADE")
    
    notif_data = exec_sql("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='notifications' AND column_name='read'")
    if notif_data:
        print("  [ ] Migration 042: notifications.read column still exists (duplicate of is_read)")
    else:
        print("  [x] Migration 042: notifications.read already cleaned up")


if __name__ == "__main__":
    main()
