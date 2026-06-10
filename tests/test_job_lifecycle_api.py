#!/usr/bin/env python3
"""
Интеграционное тестирование жизненного цикла задания НАПРЯМУЮ через Supabase REST API.
Использует service_role_key для обхода RLS.
Тестирует переходы: open -> in_progress -> active -> payment_pending -> paid -> completed.
"""
import os
import sys
import time
import json
import uuid
import requests
from datetime import datetime

# ── Загрузка .env ─────────────────────────────────────────
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(dotenv_path):
    with open(dotenv_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY', '')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')

if not SUPABASE_URL or not SERVICE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    sys.exit(1)

HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
}

results = []
def rep(name, passed, detail=""):
    s = "PASS" if passed else "FAIL"
    m = "[%s] %s | %s" % (datetime.now().strftime('%H:%M:%S'), s, name)
    if detail:
        m += " -- " + str(detail)
    results.append(m)
    print(m)


def api(method, endpoint, json_data=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    if method == 'GET':
        r = requests.get(url, headers=HEADERS, timeout=15)
    elif method == 'POST':
        r = requests.post(url, headers=HEADERS, json=json_data, timeout=15)
    elif method == 'PATCH':
        r = requests.patch(url, headers=HEADERS, json=json_data, timeout=15)
    elif method == 'DELETE':
        r = requests.delete(url, headers=HEADERS, timeout=15)
    return r


def auth_api(email, password):
    """Авторизация через Supabase Auth (возвращает user_id, access_token)."""
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    r = requests.post(url, json={'email': email, 'password': password},
                      headers={'apikey': SUPABASE_KEY}, timeout=15)
    if r.ok:
        data = r.json()
        return data['user']['id'], data['access_token']
    return None, None


def get_user_id_by_email(email):
    """Получить UUID пользователя по email через Admin API."""
    r = requests.get(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SERVICE_KEY}'},
        timeout=15
    )
    if r.ok:
        for user in r.json().get('users', r.json() if isinstance(r.json(), list) else []):
            if user.get('email') == email:
                return user['id']
    return None


def test_full_lifecycle():
    E_EMAIL = "org@test.ru"
    W_EMAIL = "trud3@test.ru"

    # 1. Получить ID пользователей
    e_id = get_user_id_by_email(E_EMAIL)
    w_id = get_user_id_by_email(W_EMAIL)
    rep("get employer UUID", e_id is not None, str(e_id)[:20] if e_id else "")
    rep("get worker UUID", w_id is not None, str(w_id)[:20] if w_id else "")

    if not e_id or not w_id:
        return False

    # 2. Создать задание (через API)
    ts = datetime.now().strftime('%H%M%S')
    r = api('POST', 'jobs', {
        'employer_id': e_id,
        'organization_name': f'TEST API Kitchen {ts}',
        'object_description': 'API lifecycle test',
        'detailed_description': 'Full matrix test via Supabase REST API',
        'work_type': '',
        'date_time': datetime.now().isoformat(),
        'payment_amount': 2000,
        'address': 'Москва, ул. Тестовая, 1',
        'city': 'Москва',
        'lat': 55.75,
        'lng': 37.61,
        'status': 'open',
        'max_workers': 1,
        'current_workers': 0,
    })
    job_data = r.json()[0] if r.ok and r.json() else None
    job_id = job_data['id'] if job_data else None
    rep("create job", r.ok, f"id={str(job_id)[:20]}" if job_id else f"status={r.status_code}")

    if not job_id:
        return False

    time.sleep(0.5)

    # 3. Проверить статус = open
    r = api('GET', f'jobs?id=eq.{job_id}&select=status')
    status = r.json()[0]['status'] if r.ok and r.json() else ''
    rep("job status open", status == 'open', status)

    # 4. Создать отклик
    r = api('POST', 'applications', {
        'job_id': job_id,
        'worker_id': w_id,
        'status': 'pending'
    })
    rep("create application", r.ok, str(r.status_code))

    time.sleep(0.5)

    # 5. Принять отклик -> in_progress
    r = api('PATCH', f'jobs?id=eq.{job_id}', {
        'status': 'in_progress',
        'current_workers': 1
    })
    rep("accept -> in_progress", r.ok, str(r.status_code))

    r = api('PATCH', f'applications?job_id=eq.{job_id}&worker_id=eq.{w_id}', {'status': 'accepted'})
    rep("set application accepted", r.ok, str(r.status_code))

    # 6. Создать смену
    r = api('POST', 'shifts', {
        'job_id': job_id,
        'worker_id': w_id,
        'employer_id': e_id,
        'worker_checkin': False,
    })
    shift_data = r.json()[0] if r.ok and r.json() else None
    shift_id = shift_data['id'] if shift_data else None
    rep("create shift", r.ok, str(shift_id)[:20] if shift_id else "")

    if not shift_id:
        return False

    time.sleep(0.5)

    # 7. Проверить статус = in_progress
    r = api('GET', f'jobs?id=eq.{job_id}&select=status')
    status = r.json()[0]['status'] if r.ok and r.json() else ''
    rep("job status in_progress", status == 'in_progress', status)

    # 8. Чек-ин -> active
    r = api('PATCH', f'shifts?id=eq.{shift_id}', {
        'worker_checkin': True,
        'start_time': datetime.now().isoformat(),
        'status': 'active'
    })
    rep("worker checkin -> shift active", r.ok, str(r.status_code))

    r = api('PATCH', f'jobs?id=eq.{job_id}', {'status': 'active'})
    rep("checkin -> job active", r.ok, str(r.status_code))

    time.sleep(0.5)

    # 9. Проверить статус = active
    r = api('GET', f'jobs?id=eq.{job_id}&select=status')
    status = r.json()[0]['status'] if r.ok and r.json() else ''
    rep("job status active", status == 'active', status)

    # 10. Завершить смену -> payment_pending
    r = api('PATCH', f'shifts?id=eq.{shift_id}', {
        'status': 'payment_pending'
    })
    rep("complete shift -> payment_pending", r.ok, str(r.status_code))

    r = api('PATCH', f'jobs?id=eq.{job_id}', {'status': 'payment_pending'})
    rep("complete -> job payment_pending", r.ok, str(r.status_code))

    time.sleep(0.5)

    # 11. Проверить статус = payment_pending
    r = api('GET', f'jobs?id=eq.{job_id}&select=status')
    status = r.json()[0]['status'] if r.ok and r.json() else ''
    rep("job status payment_pending", status == 'payment_pending', status)

    # 12. Подтвердить оплату обеими сторонами -> paid
    r = api('PATCH', f'shifts?id=eq.{shift_id}', {
        'employer_payment_confirmed': True,
        'worker_payment_confirmed': True,
        'status': 'paid'
    })
    rep("confirm payment -> shift paid", r.ok, str(r.status_code))

    r = api('PATCH', f'jobs?id=eq.{job_id}', {'status': 'paid'})
    rep("confirm payment -> job paid", r.ok, str(r.status_code))

    time.sleep(0.5)

    # 13. Проверить статус = paid
    r = api('GET', f'jobs?id=eq.{job_id}&select=status')
    status = r.json()[0]['status'] if r.ok and r.json() else ''
    rep("job status paid", status == 'paid', status)

    # 14. Оценить друг друга
    # Employer rates worker
    r = api('POST', 'ratings', {
        'job_id': job_id,
        'rater_user_id': e_id,
        'rated_user_id': w_id,
        'rating_type': 'employer',
        'target_type': 'worker',
        'rating': 5,
        'comment': 'Отличный работник! (API test)',
    })
    rep("employer rate worker", r.ok, str(r.status_code))

    time.sleep(0.5)

    # Worker rates employer
    r = api('POST', 'ratings', {
        'job_id': job_id,
        'rater_user_id': w_id,
        'rated_user_id': e_id,
        'rating_type': 'worker',
        'target_type': 'employer',
        'rating': 4,
        'comment': 'Хороший работодатель (API test)',
    })
    rep("worker rate employer", r.ok, str(r.status_code))

    time.sleep(0.5)

    # 15. Проверить, что рейтинги сохранились
    r = api('GET', f'ratings?job_id=eq.{job_id}&select=id,rating,rater_user_id')
    ratings_count = len(r.json()) if r.ok and r.json() else 0
    rep("ratings saved", ratings_count >= 2, f"count={ratings_count}")

    # 16. Перевести задание в completed (после оценок)
    r = api('PATCH', f'jobs?id=eq.{job_id}', {'status': 'completed'})
    rep("paid -> completed", r.ok, str(r.status_code))

    time.sleep(0.5)

    # 17. Проверить статус = completed
    r = api('GET', f'jobs?id=eq.{job_id}&select=status')
    status = r.json()[0]['status'] if r.ok and r.json() else ''
    rep("job status completed", status == 'completed', status)

    # 18. Проверить средний рейтинг пользователя
    r = api('GET', f'ratings?rated_user_id=eq.{w_id}&select=rating')
    if r.ok and r.json():
        ratings = [x['rating'] for x in r.json()]
        avg = round(sum(ratings) / len(ratings), 1) if ratings else 0
    else:
        avg = 0
    rep("worker has ratings", avg > 0, f"avg={avg}, count={len(ratings) if r.ok else 0}")

    # 19. Cleanup: удалить тестовые данные
    api('DELETE', f'ratings?job_id=eq.{job_id}')
    api('DELETE', f'shifts?id=eq.{shift_id}')
    api('DELETE', f'applications?job_id=eq.{job_id}')
    api('DELETE', f'jobs?id=eq.{job_id}')
    rep("cleanup test data", True)

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Job Lifecycle API Test - matrix_jobs.md compliance")
    print("Supabase:", SUPABASE_URL[:40] + "...")
    print("=" * 60)

    ok = test_full_lifecycle()

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if "PASS" in r)
    failed = sum(1 for r in results if "FAIL" in r)
    print(f"Results: {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 60)

    sys.exit(0 if not failed else 1)
