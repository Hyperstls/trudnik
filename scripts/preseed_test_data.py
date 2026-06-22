"""
Предзаполнение тестовых данных через Supabase REST API (service_role ключ).

Создаёт задания, отклики, приглашения, рейтинги и чаты напрямую в БД,
минуя Flask. Это решает проблему 15-секундных таймаутов Supabase —
HTTP-тесты находят уже готовые данные и не пропускаются.

Запускать ПЕРЕД тестами:
    python scripts/preseed_test_data.py

Удалять ПОСЛЕ тестов:
    python scripts/cleanup_test_data.py
"""

import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')

if not SUPABASE_URL or not SERVICE_KEY:
    print('ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env')
    sys.exit(1)

PROTECTED_EMAILS = {'org@test.ru', 'trud@test.ru', 'admin@test.ru'}

REST_HEADERS = {
    'Authorization': f'Bearer {SERVICE_KEY}',
    'apikey': SERVICE_KEY,
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
}

AUTH_HEADERS = {
    'Authorization': f'Bearer {SERVICE_KEY}',
    'apikey': SERVICE_KEY,
}

# ── Хелперы ──────────────────────────────────────────────


def get_user_ids():
    """Возвращает {email: user_id} для защищённых пользователей."""
    url = f'{SUPABASE_URL}/auth/v1/admin/users'
    resp = requests.get(url, headers=AUTH_HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f'ERROR: Auth API returned {resp.status_code}: {resp.text[:200]}')
        sys.exit(1)

    data = resp.json()
    users = data.get('users', []) if isinstance(data, dict) else data

    result = {}
    for u in users:
        email = (u.get('email') or '').lower().strip()
        if email in PROTECTED_EMAILS:
            result[email] = u.get('id')
    return result


def post_record(table: str, data: dict) -> dict | None:
    """Создаёт запись в таблице Supabase."""
    url = f'{SUPABASE_URL}/rest/v1/{table}'
    resp = requests.post(url, headers=REST_HEADERS, json=data, timeout=30)
    if resp.status_code in (200, 201):
        result = resp.json()
        if isinstance(result, list) and len(result) > 0:
            return result[0]
        return result
    else:
        print(f'  WARNING: POST {table} returned {resp.status_code}: {resp.text[:200]}')
        return None


def delete_previous_test_data(employer_id: str, worker_id: str):
    """Удаляет предыдущие тестовые данные."""
    tables_cols = [
        ('messages', 'sender_id'),
        ('ratings', 'rater_user_id'),
        ('ratings', 'rated_user_id'),
        ('favorites', 'user_id'),
        ('invitations', 'employer_id'),
        ('invitations', 'worker_id'),
        ('blacklists', 'user_id'),
        ('applications', 'worker_id'),
        ('jobs', 'employer_id'),
    ]
    for table, col in tables_cols:
        for uid in [employer_id, worker_id]:
            url = f'{SUPABASE_URL}/rest/v1/{table}?{col}=eq.{uid}'
            try:
                requests.delete(url, headers=REST_HEADERS, timeout=30)
            except Exception:
                pass


# ── Основная логика ──────────────────────────────────────


def main(fail_on_error: bool = True) -> bool:
    """Основная логика предзаполнения тестовых данных.

    Args:
        fail_on_error: Если True — sys.exit(1) при ошибке. Если False — возвращает False.

    Returns:
        True если всё успешно, False при ошибке.
    """
    print('=' * 60)
    print('Supabase Test Data Preseed Script')
    print('=' * 60)
    print(f'Supabase URL: {SUPABASE_URL}')
    print()

    # 1. Получаем ID пользователей
    print('[1/7] Fetching user IDs...')
    user_ids = get_user_ids()
    employer_id = user_ids.get('org@test.ru')
    worker_id = user_ids.get('trud@test.ru')
    admin_id = user_ids.get('admin@test.ru')

    if not employer_id or not worker_id:
        msg = f'ERROR: Protected users not found. employer_id={employer_id}, worker_id={worker_id}'
        print(msg)
        if fail_on_error:
            sys.exit(1)
        return False

    print(f'  Employer: org@test.ru = {employer_id}')
    print(f'  Worker:   trud@test.ru = {worker_id}')
    print(f'  Admin:    admin@test.ru = {admin_id}')
    print()

    # 1b. Fix admin role
    if admin_id:
        patch_url = f'{SUPABASE_URL}/rest/v1/profiles?id=eq.{admin_id}'
        patch_resp = requests.patch(
            patch_url,
            headers=REST_HEADERS,
            json={'role': 'admin'},
            timeout=30,
        )
        print(f'  Admin role fix: {patch_resp.status_code}')

    # 2. Удаляем старые тестовые данные
    print('[2/7] Cleaning previous test data...')
    delete_previous_test_data(employer_id, worker_id)
    print('  Done.')
    print()

    now = datetime.now(timezone.utc)
    future = now + timedelta(days=30)
    past = now - timedelta(days=1)

    # 3. Создаём задания
    print('[3/7] Creating test jobs...')

    default_lat = 55.7558
    default_lng = 37.6173

    job1 = post_record('jobs', {
        'employer_id': employer_id,
        'organization_name': 'Тестовое задание OPEN',
        'org_description': '',
        'object_description': '',
        'work_type': 'разовая',
        'detailed_description': 'Открытое задание для тестирования откликов',
        'date_time': future.isoformat(),
        'payment_amount': 5000,
        'address': 'ул. Тестовая, 1',
        'city': 'Москва',
        'lat': default_lat,
        'lng': default_lng,
        'preferred_religion': '',
        'max_workers': 5,
        'current_workers': 0,
        'status': 'open',
        'expires_at': future.isoformat(),
    })

    job2 = post_record('jobs', {
        'employer_id': employer_id,
        'organization_name': 'Тестовое задание COMPLETED',
        'org_description': '',
        'object_description': '',
        'work_type': 'разовая',
        'detailed_description': 'Завершённое задание для тестирования рейтингов',
        'date_time': now.isoformat(),
        'payment_amount': 7000,
        'address': 'ул. Тестовая, 2',
        'city': 'Санкт-Петербург',
        'lat': default_lat,
        'lng': default_lng,
        'preferred_religion': '',
        'max_workers': 3,
        'current_workers': 0,
        'status': 'completed',
        'expires_at': now.isoformat(),
    })

    job3 = post_record('jobs', {
        'employer_id': employer_id,
        'organization_name': 'Тестовое задание CANCELLED',
        'org_description': '',
        'object_description': '',
        'work_type': 'разовая',
        'detailed_description': 'Отозванное задание для тестирования восстановления',
        'date_time': future.isoformat(),
        'payment_amount': 3000,
        'address': 'ул. Тестовая, 3',
        'city': 'Казань',
        'lat': default_lat,
        'lng': default_lng,
        'preferred_religion': '',
        'max_workers': 2,
        'current_workers': 0,
        'status': 'cancelled',
        'expires_at': future.isoformat(),
    })

    job1_id = job1.get('id') if job1 else None
    job2_id = job2.get('id') if job2 else None
    job3_id = job3.get('id') if job3 else None

    print(f'  Job OPEN:      {job1_id}')
    print(f'  Job COMPLETED: {job2_id}')
    print(f'  Job CANCELLED: {job3_id}')
    print()

    if not job1_id or not job2_id:
        print('ERROR: Failed to create required jobs')
        if fail_on_error:
            sys.exit(1)
        return False

    # 4. Создаём отклики
    print('[4/7] Creating applications...')

    app1 = post_record('applications', {
        'job_id': job1_id,
        'worker_id': worker_id,
        'status': 'pending',
    })

    app2 = post_record('applications', {
        'job_id': job2_id,
        'worker_id': worker_id,
        'status': 'pending',
    })

    app1_id = app1.get('id') if app1 else None
    app2_id = app2.get('id') if app2 else None

    # NOTE: accepted-отклики больше не создаются пресидом.
    # Фикстура accepted_application_id в conftest.py сама создаёт
    # accepted через accept RPC, чтобы избежать загрязнения страниц тестов.
    print(f'  Application PENDING (job1): {app1_id}')
    print(f'  Application PENDING (job2): {app2_id}')
    print()

    # 5. Создаём приглашения (два — для accept и reject тестов)
    print('[5/7] Creating invitations...')

    inv_id = None
    inv2_id = None
    if job1_id:
        invitation = post_record('invitations', {
            'job_id': job1_id,
            'employer_id': employer_id,
            'worker_id': worker_id,
            'status': 'pending',
            'created_at': now.isoformat(),
        })
        inv_id = invitation.get('id') if invitation else None
        print(f'  Invitation 1 (job1): {inv_id}')

    if job2_id:
        # Второе приглашение на другое задание (уникальный constraint на job_id+worker_id)
        invitation2 = post_record('invitations', {
            'job_id': job2_id,
            'employer_id': employer_id,
            'worker_id': worker_id,
            'status': 'pending',
            'created_at': now.isoformat(),
        })
        inv2_id = invitation2.get('id') if invitation2 else None
        print(f'  Invitation 2 (job2): {inv2_id}')
    print()

    # 6. Создаём рейтинг
    print('[6/7] Creating rating...')

    if job2_id:
        rating = post_record('ratings', {
            'job_id': job2_id,
            'rater_user_id': employer_id,
            'rated_user_id': worker_id,
            'rating': 5,
            'comment': 'Отличный работник!',
            'rating_type': 'employer',
            'target_type': 'worker',
        })
        rating_id = rating.get('id') if rating else None
        print(f'  Rating: {rating_id}')

        # И встречный рейтинг
        rating2 = post_record('ratings', {
            'job_id': job2_id,
            'rater_user_id': worker_id,
            'rated_user_id': employer_id,
            'rating': 4,
            'comment': 'Хороший работодатель',
            'rating_type': 'worker',
            'target_type': 'employer',
        })
        rid2 = rating2.get('id') if rating2 else None
        print(f'  Rating (worker -> employer): {rid2}')
    print()

    # 7. Создаём избранное
    print('[7/7] Creating favorites...')

    if job1_id:
        fav1 = post_record('favorites', {
            'user_id': worker_id,
            'target_id': employer_id,
            'favorite_type': 'employer',
        })
        print(f'  Favorite (worker -> employer): {fav1.get("id") if fav1 else None}')

        fav2 = post_record('favorites', {
            'user_id': employer_id,
            'target_id': worker_id,
            'favorite_type': 'worker',
        })
        print(f'  Favorite (employer -> worker): {fav2.get("id") if fav2 else None}')
    print()

    # 8. Blacklist-запись НЕ создаётся пресидом.
    # Раньше создавалась запись employer→worker, но это ломало тесты,
    # в которых трудник должен откликаться на задания работодателя (403 Forbidden).
    # Тесты, которым нужен blacklist, создают его самостоятельно.
    print('[8/10] Skipping blacklist entry (created by tests that need it).')
    bl_id = None
    print()

    # 9. Устанавливаем verification_status='pending'
    print('[9/10] Setting verification_status=pending...')
    patch_url = f'{SUPABASE_URL}/rest/v1/profiles?id=eq.{worker_id}'
    patch_resp = requests.patch(
        patch_url,
        headers=REST_HEADERS,
        json={'verification_status': 'pending'},
        timeout=30,
    )
    print(f'  Worker verification_status update: {patch_resp.status_code}')
    # Также ставим employer
    patch_url2 = f'{SUPABASE_URL}/rest/v1/profiles?id=eq.{employer_id}'
    patch_resp2 = requests.patch(
        patch_url2,
        headers=REST_HEADERS,
        json={'verification_status': 'pending'},
        timeout=30,
    )
    print(f'  Employer verification_status update: {patch_resp2.status_code}')
    print()

    # 10. Устанавливаем verification_status для админ-тестов
    # (таблицы verification_requests нет в схеме — статус хранится в profiles)
    print('[10/10] Setting verification data...')
    vr_url = f'{SUPABASE_URL}/rest/v1/profiles?id=eq.{employer_id}'
    vr_resp = requests.patch(
        vr_url,
        headers=REST_HEADERS,
        json={
            'verification_status': 'pending',
            'inn': '7700000000',
        },
        timeout=30,
    )
    vr_id = employer_id  # verification привязана к профилю
    print(f'  Verification data set on profile: {employer_id} (status={vr_resp.status_code})')
    print()

    # Создаём employer_details для компании
    ed = post_record('employer_details', {
        'user_id': employer_id,
        'company_name': 'ООО Тест',
        'inn': '7700000000',
    })
    ed_id = ed.get('id') if ed else None
    print(f'  Employer details: {ed_id}')
    print()

    print('=' * 60)
    print('Preseed complete!')
    print(f'Jobs: {job1_id}, {job2_id}, {job3_id}')
    print(f'Applications: {app1_id}, {app2_id}')
    print(f'Invitation: {inv_id if job1_id else "N/A"}')
    print(f'Ratings created')
    print(f'Favorites created')
    print(f'Blacklist: {bl_id}')
    print(f'Verification data: employer profile {vr_id}, employer_details {ed_id}')
    print('=' * 60)
    return True


if __name__ == '__main__':
    main(fail_on_error=True)
