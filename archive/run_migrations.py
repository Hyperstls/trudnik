#!/usr/bin/env python3
"""Применение миграций SQL к Supabase. Запуск: python run_migrations.py"""
import os, sys
import requests
from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
if not SUPABASE_URL or not SERVICE_KEY:
    print("❌ SUPABASE_URL или SUPABASE_SERVICE_ROLE_KEY не заданы в .env")
    sys.exit(1)

HEADERS = {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}", "Content-Type": "application/json"}

MIGRATIONS = ["003_add_max_workers", "004_fix_notifications", "005_add_is_read_column",
    "006_add_monetization", "007_add_skills_religions", "008_add_sort_order",
    "009_fix_user_skills_rls", "010_add_shifts_update_rls", "011_add_search_indexes",
    "012_notification_prefs", "013_invitations", "014_add_contact_field"]

def run_sql(sql):
    resp = requests.post(f"{SUPABASE_URL}/sql", headers=HEADERS, json={"query": sql}, timeout=60)
    if resp.status_code in (200, 201): return True
    print(f"  [{resp.status_code}] {str(resp.json())[:200]}")
    return False

print(f"Supabase: {SUPABASE_URL}")
for m in MIGRATIONS:
    path = f"migrations/{m}.sql"
    if not os.path.exists(path): continue
    sql = open(path, encoding="utf-8").read()
    print(f"{m}...", end=" ")
    print("✅" if run_sql(sql) else "❌ (игнорируем, если уже применена)")
print("Готово.")
