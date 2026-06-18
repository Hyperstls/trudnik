"""
Скрипт очистки тестовых данных через Supabase REST API (service_role ключ).

Удаляет всех пользователей КРОМЕ: org@test.ru, trud@test.ru, admin@test.ru
и все их задания/отклики/профили.

Использует REST API, НЕ прямой SQL.
"""
import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')

if not SUPABASE_URL or not SERVICE_KEY:
    print('ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env')
    sys.exit(1)

PROTECTED_EMAILS = {'org@test.ru', 'trud@test.ru', 'admin@test.ru'}

# Заголовки для REST API (service_role)
REST_HEADERS = {
    'Authorization': f'Bearer {SERVICE_KEY}',
    'apikey': SERVICE_KEY,
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal',
}

# Заголовки для Auth Admin API
AUTH_HEADERS = {
    'Authorization': f'Bearer {SERVICE_KEY}',
    'apikey': SERVICE_KEY,
}


def get_all_users():
    """Получить список всех пользователей через Auth Admin API."""
    url = f'{SUPABASE_URL}/auth/v1/admin/users'
    resp = requests.get(url, headers=AUTH_HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f'  ERROR: GET /auth/v1/admin/users returned {resp.status_code}: {resp.text[:200]}')
        return []
    data = resp.json()
    # Supabase returns either {'users': [...]} or a list directly
    if isinstance(data, dict):
        return data.get('users', [])
    return data if isinstance(data, list) else []


def get_all_profiles():
    """Получить все профили через REST API (service_role)."""
    url = f'{SUPABASE_URL}/rest/v1/profiles?select=id,email'
    resp = requests.get(url, headers=REST_HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f'  ERROR: GET profiles returned {resp.status_code}: {resp.text[:200]}')
        return []
    return resp.json()


def get_all_emails_from_auth():
    """Получить email'ы всех пользователей через Auth Admin API (пагинация)."""
    all_users = []
    page = 1
    per_page = 100
    while True:
        url = f'{SUPABASE_URL}/auth/v1/admin/users?page={page}&per_page={per_page}'
        resp = requests.get(url, headers=AUTH_HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f'  ERROR: Auth API page {page} returned {resp.status_code}')
            break
        data = resp.json()
        users = data.get('users', []) if isinstance(data, dict) else data
        if not users:
            break
        all_users.extend(users)
        if len(users) < per_page:
            break
        page += 1
    return all_users


def delete_user_auth(user_id):
    """Удалить пользователя из Auth системы."""
    url = f'{SUPABASE_URL}/auth/v1/admin/users/{user_id}'
    resp = requests.delete(url, headers=AUTH_HEADERS, timeout=30)
    return resp.status_code in (200, 202, 204)


def delete_records(table, column, value):
    """Удалить записи из таблицы по условию (column=eq.value)."""
    url = f'{SUPABASE_URL}/rest/v1/{table}?{column}=eq.{value}'
    resp = requests.delete(url, headers=REST_HEADERS, timeout=30)
    return resp.status_code in (200, 204)


def delete_user_data(uid):
    """Удалить все связанные данные пользователя через REST API."""
    tables_columns = [
        ('jobs', 'employer_id'),
        ('applications', 'worker_id'),
        ('applications', 'employer_id'),
        ('profiles', 'id'),
        ('user_skills', 'user_id'),
        ('push_subscriptions', 'user_id'),
        ('ratings', 'rater_id'),
        ('ratings', 'rated_user_id'),
        ('favorites', 'user_id'),
        ('favorites', 'favorited_user_id'),
        ('invitations', 'employer_id'),
        ('invitations', 'worker_id'),
        ('blacklists', 'user_id'),
        ('blacklists', 'blocked_user_id'),
        ('notification_prefs', 'user_id'),
        ('notifications', 'user_id'),
        ('messages', 'sender_id'),
        ('messages', 'receiver_id'),
        ('chat_rooms', 'employer_id'),
        ('chat_rooms', 'worker_id'),
        ('email_log', 'user_id'),
    ]
    for table, col in tables_columns:
        try:
            delete_records(table, col, uid)
        except Exception as e:
            print(f'    Warning: {table}.{col}={uid} delete failed: {e}')


def main():
    print('=' * 60)
    print('Supabase Data Cleanup Script')
    print('=' * 60)
    print(f'Protected emails: {PROTECTED_EMAILS}')
    print(f'Supabase URL: {SUPABASE_URL}')
    print()

    # Шаг 1: Получить всех пользователей через Auth API
    print('[1/5] Fetching all auth users (with pagination)...')
    users = get_all_emails_from_auth()
    print(f'  Found {len(users)} total users')

    if users:
        # Разделяем на защищённых и на удаление
        protected_ids = set()
        users_to_delete = []

        for u in users:
            email = (u.get('email') or '').lower().strip()
            uid = u.get('id', '')
            if email in PROTECTED_EMAILS:
                protected_ids.add(uid)
                print(f'  [PROTECTED] {email} (id={uid})')
            else:
                users_to_delete.append(u)
                print(f'  [DELETE]    {email} (id={uid})')

        if not users_to_delete:
            print('\n  No users to delete. Only protected users found.')
        else:
            print(f'\n[2/5] Deleting {len(users_to_delete)} users and their data...')
            deleted = 0
            for u in users_to_delete:
                uid = u.get('id', '')
                email = u.get('email', 'unknown')

                # Удаляем связанные данные
                delete_user_data(uid)

                # Удаляем пользователя из Auth
                ok = delete_user_auth(uid)
                if ok:
                    deleted += 1
                    print(f'  [{deleted}/{len(users_to_delete)}] Deleted: {email}')
                else:
                    print(f'  [{deleted}/{len(users_to_delete)}] FAILED: {email}')

                time.sleep(0.05)

            print(f'  Result: {deleted}/{len(users_to_delete)} deleted successfully')
    else:
        print('  Auth API returned no users. Falling back to profiles...')
        profiles = get_all_profiles()
        print(f'  Found {len(profiles)} profiles')

        protected_ids = set()
        users_to_delete = []

        for p in profiles:
            email = (p.get('email') or '').lower().strip()
            pid = p.get('id', '')
            if email in PROTECTED_EMAILS:
                protected_ids.add(pid)
                print(f'  [PROTECTED] {email} (id={pid})')
            else:
                users_to_delete.append(p)
                print(f'  [DELETE]    {email} (id={pid})')

        if users_to_delete:
            print(f'\n[2/5] Deleting {len(users_to_delete)} users via profiles...')
            deleted = 0
            for p in users_to_delete:
                uid = p.get('id', '')
                email = p.get('email', 'unknown')
                delete_user_data(uid)
                delete_user_auth(uid)
                deleted += 1
                print(f'  [{deleted}/{len(users_to_delete)}] Deleted: {email}')
                time.sleep(0.05)
            print(f'  Result: {deleted}/{len(users_to_delete)} deleted')

    # Шаг 3: Удалить осиротевшие задания
    print('\n[3/5] Cleaning orphaned jobs...')
    jobs_url = f'{SUPABASE_URL}/rest/v1/jobs?select=id,employer_id'
    jobs_resp = requests.get(jobs_url, headers=REST_HEADERS, timeout=30)
    if jobs_resp.status_code == 200:
        jobs = jobs_resp.json()
        orphaned = [j for j in jobs if j.get('employer_id') not in protected_ids]
        if orphaned:
            for j in orphaned:
                delete_records('jobs', 'id', j['id'])
            print(f'  Deleted {len(orphaned)} orphaned jobs')
        else:
            print('  No orphaned jobs found')
    else:
        print(f'  Could not fetch jobs: {jobs_resp.status_code}')

    # Шаг 4: Финальная верификация
    print('\n[4/5] Final verification...')
    final_users = get_all_emails_from_auth()
    if final_users:
        print(f'  Remaining users: {len(final_users)}')
        remaining_emails = set()
        for u in final_users:
            email = u.get('email', 'unknown')
            remaining_emails.add(email)
            status = 'PROTECTED' if email in PROTECTED_EMAILS else 'UNEXPECTED'
            mark = '[OK]' if status == 'PROTECTED' else '[!!]'
            print(f'    {mark} {email} -- {status}')

        if remaining_emails == PROTECTED_EMAILS:
            print('  [OK] All 3 protected users remain, no extra users!')
        else:
            extra = remaining_emails - PROTECTED_EMAILS
            missing = PROTECTED_EMAILS - remaining_emails
            if extra:
                print(f'  [!!] Extra users found: {extra}')
            if missing:
                print(f'  [!!] Missing protected users: {missing}')
    else:
        # Fallback: profiles
        final_profiles = get_all_profiles()
        print(f'  Remaining profiles: {len(final_profiles)}')
        remaining_emails = set()
        for p in final_profiles:
            email = p.get('email', 'unknown')
            remaining_emails.add(email)
            status = 'PROTECTED' if email in PROTECTED_EMAILS else 'UNEXPECTED'
            mark = '[OK]' if status == 'PROTECTED' else '[!!]'
            print(f'    {mark} {email} -- {status}')

        if remaining_emails == PROTECTED_EMAILS:
            print('  [OK] All 3 protected users remain, no extra users!')
        else:
            extra = remaining_emails - PROTECTED_EMAILS
            missing = PROTECTED_EMAILS - remaining_emails
            if extra:
                print(f'  [!!] Extra users found: {extra}')
            if missing:
                print(f'  [!!] Missing protected users: {missing}')

    print('\n[5/5] Cleanup complete!')
    print('=' * 60)


if __name__ == '__main__':
    main()
