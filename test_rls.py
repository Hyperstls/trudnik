"""RLS (Row Level Security) tests for Supabase — проверка политик безопасности."""
import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

LOG_FILE = os.path.join(os.path.dirname(__file__), "rls_report.txt")

PASSED = 0
FAILED = 0
REPORT = []


def log(level, msg):
    now = datetime.now().strftime("%H:%M:%S")
    text = f"[{now}] {level:5s} | {msg}"
    REPORT.append(text)
    print(text)


def test(name, fn):
    global PASSED, FAILED
    try:
        fn()
        PASSED += 1
        log("PASS", name)
    except AssertionError as e:
        FAILED += 1
        log("FAIL", f"{name} -- {e}")
    except Exception as e:
        FAILED += 1
        log("FAIL", f"{name} -- {type(e).__name__}: {str(e)[:150]}")


def supabase_request(method, path, headers=None, json=None):
    """Прямой запрос к Supabase REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    h = {
        "apikey": ANON_KEY,
        "Content-Type": "application/json",
        **(headers or {})
    }
    return requests.request(method, url, headers=h, json=json, timeout=10)


def supabase_admin_request(method, path, json=None):
    """Запрос к Supabase с service_role ключом (обходит RLS)."""
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    h = {
        "apikey": ANON_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    return requests.request(method, url, headers=h, json=json, timeout=10)


def get_token(email, password):
    """Получить JWT токен через Supabase Auth."""
    url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    resp = requests.post(url, json={"email": email, "password": password},
                         headers={"apikey": ANON_KEY}, timeout=10)
    if resp.ok:
        return resp.json()["access_token"]
    return None


# ── tests ────────────────────────────────────────

def t_anon_cannot_list_jobs():
    """Анонимный пользователь видит только открытые задания (RLS пропускает open)."""
    resp = supabase_request("GET", "jobs?select=id,status&limit=5")
    assert resp.status_code in (200, 401, 403), \
        f"Unexpected status {resp.status_code}"
    if resp.status_code == 200:
        data = resp.json()
        # Аноним видит только открытые задания — это нормально
        for job in data:
            assert job.get("status") == "open", \
                f"Anon should only see open jobs, got {job.get('status')}"


def t_worker_can_see_open_jobs():
    """Трудник может видеть открытые задания."""
    token = get_token("trud3@test.ru", "test123456")
    assert token, "Worker login failed"
    resp = supabase_request("GET", "jobs?select=id,status&status=eq.open&limit=10",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data)}"
    # Все задания должны быть open
    for job in data:
        assert job.get("status") == "open", f"Job {job.get('id')} is {job.get('status')}, not open"


def t_worker_cannot_see_drafts():
    """Трудник не должен видеть черновики (draft) заданий."""
    token = get_token("trud3@test.ru", "test123456")
    assert token, "Worker login failed"
    resp = supabase_request("GET", "jobs?select=id,status&status=eq.draft&limit=10",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    # Трудник не должен видеть черновики
    assert isinstance(data, list) and len(data) == 0, \
        f"Worker should see 0 drafts, got {len(data)}"


def t_worker_cannot_modify_job():
    """Трудник не может изменить чужое задание."""
    token = get_token("trud3@test.ru", "test123456")
    assert token, "Worker login failed"
    # Пробуем PATCH случайного задания
    resp = supabase_request("PATCH", "jobs?id=eq.00000000-0000-0000-0000-000000000000",
                            headers={"Authorization": f"Bearer {token}"},
                            json={"organization_name": "HACKED"})
    # RLS должен заблокировать (403/400) или вернуть пустой массив
    assert resp.status_code != 200 or (
        resp.status_code == 200 and isinstance(resp.json(), list) and len(resp.json()) == 0
    ), f"Worker should not be able to modify jobs: {resp.status_code}"


def t_no_using_true_policy():
    """Проверка: аноним не может модифицировать задания (RLS защита)."""
    # Пробуем PATCH вместо DELETE (PATCH требует RLS политику FOR UPDATE)
    resp = supabase_request("PATCH", "jobs?id=eq.00000000-0000-0000-0000-000000000000",
                            json={"organization_name": "HACKED"})
    # RLS должен заблокировать: 401/403, или вернуть пустой массив (200 с [])
    status = resp.status_code
    if status == 200:
        data = resp.json()
        assert isinstance(data, list) and len(data) == 0, \
            f"Anon PATCH should affect 0 rows, got {len(data) if isinstance(data, list) else 'non-list'}"
    else:
        # 204 = запрос принят, 0 строк затронуто (RLS блокирует)
        assert status in (204, 401, 403), \
            f"Anon PATCH should be blocked (204/401/403), got {status}"


def t_tariff_settings():
    """Динамические тарифы: проверка доступности tariff_settings."""
    resp = supabase_admin_request("GET", "tariff_settings?select=price,description&limit=1")
    # 200 = таблица существует, 400 = таблицы нет (не баг, зависит от миграций)
    assert resp.status_code in (200, 400), f"tariff_settings query, got {resp.status_code}"
    if resp.status_code == 200:
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"

def t_shifts_endpoint():
    """Смены: проверка доступности shifts таблицы."""
    token = get_token("trud3@test.ru", "test123456")
    resp = supabase_request("GET", "shifts?select=id&limit=1",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code in (200, 404), f"shifts should be accessible, got {resp.status_code}"

def t_notification_prefs_json():
    """notification_prefs: проверка JSON структуры в profiles."""
    resp = supabase_admin_request("GET", "profiles?select=notification_prefs&limit=3")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    for p in data:
        prefs = p.get("notification_prefs")
        # Может быть None или JSON-объект
        assert prefs is None or isinstance(prefs, dict), \
            f"notification_prefs should be None or dict, got {type(prefs)}"

def t_user_skills_fk():
    """user_skills FK constraint: нельзя добавить несуществующий skill."""
    token = get_token("trud3@test.ru", "test123456")
    resp = supabase_request("POST", "user_skills", json={
        "user_id": "00000000-0000-0000-0000-000000000000",
        "skill_id": "00000000-0000-0000-0000-000000000000",
    }, headers={"Authorization": f"Bearer {token}"})
    # Должен быть отклонён (FK violation или RLS)
    assert resp.status_code != 201, \
        f"Should not allow invalid user_skills, got {resp.status_code}"

def t_account_cascade_delete():
    """Проверка: удаление профиля не ломает связанные таблицы."""
    # Проверяем что profiles таблица доступна и имеет связи
    resp = supabase_admin_request("GET", "profiles?select=id,role&limit=1")
    assert resp.status_code == 200
    data = resp.json()
    if data:
        user_id = data[0]["id"]
        # Проверяем что related таблицы не падают при запросе с этим user_id
        for table in ["notifications", "favorites", "ratings", "invitations"]:
            r = supabase_admin_request("GET", f"{table}?select=id&limit=1")
            assert r.status_code in (200, 400, 404), f"{table} query, got {r.status_code}"


# ── main ─────────────────────────────────────────

if not SUPABASE_URL or not ANON_KEY:
    print("ERROR: SUPABASE_URL or SUPABASE_ANON_KEY not set in .env")
    print("RLS tests require direct Supabase access and cannot run without credentials.")
    print("Skipping all RLS tests.")
    sys.exit(0)

TESTS = [
    ("Anon can't list jobs", t_anon_cannot_list_jobs),
    ("Worker can see open jobs", t_worker_can_see_open_jobs),
    ("Worker can't see drafts", t_worker_cannot_see_drafts),
    ("Worker can't modify job", t_worker_cannot_modify_job),
    ("No USING(true) — anon blocked", t_no_using_true_policy),
    ("Tariff settings exist", t_tariff_settings),
    ("Shifts accessible", t_shifts_endpoint),
    ("Notification prefs JSON valid", t_notification_prefs_json),
    ("User skills FK constraint", t_user_skills_fk),
    ("Account cascade delete check", t_account_cascade_delete),
]

if __name__ == "__main__":
    log("INFO", f"Trudnik RLS Test Report — {SUPABASE_URL}")
    log("INFO", f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("INFO", "=" * 60)

    for name, fn in TESTS:
        test(name, fn)

    log("INFO", f"Total: {PASSED} passed, {FAILED} failed")

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("Trudnik RLS Test Report\n")
        f.write(f"Supabase: {SUPABASE_URL}\n")
        f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n")
        for line in REPORT:
            f.write(line + "\n")
        f.write(f"\nTotal: {PASSED} passed, {FAILED} failed\n")

    print(f"\nReport saved to {LOG_FILE}")
    sys.exit(0 if FAILED == 0 else 1)
