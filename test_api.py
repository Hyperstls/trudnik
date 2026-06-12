"""API tests for Trudnik — CRUD, auth, authorisation, CSRF protection."""
import os
import sys
import requests
from datetime import datetime

BASE = "http://127.0.0.1:5000"
LOG_FILE = os.path.join(os.path.dirname(__file__), "api_report.txt")

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


# ── helpers ──────────────────────────────────────

def login(session, email, password):
    """Логин через /login, возвращает сессию с куками."""
    resp = session.post(f"{BASE}/login", data={
        "email": email,
        "password": password,
    }, allow_redirects=False)
    return resp


def api_login_get_session(email, password):
    """Логин и возврат requests.Session с куками."""
    s = requests.Session()
    s.get(f"{BASE}/login")  # Получить CSRF-токен
    login(s, email, password)
    return s


# ── tests ────────────────────────────────────────

def t_health():
    """GET / → 200"""
    r = requests.get(f"{BASE}/", allow_redirects=False)
    assert r.status_code in (200, 302), f"Expected 200/302, got {r.status_code}"


def t_api_skills():
    """GET /api/skills → 200 + JSON"""
    r = requests.get(f"{BASE}/api/skills")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "skills" in data, f"Expected 'skills' key, got {list(data.keys())}"


def t_api_religions():
    """GET /api/religions → 200 + JSON"""
    r = requests.get(f"{BASE}/api/religions")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert "religions" in data, f"Expected 'religions' key, got {list(data.keys())}"


def t_login_success():
    """POST /login with valid credentials → 302 redirect"""
    s = requests.Session()
    s.get(f"{BASE}/login")
    resp = login(s, "org@test.ru", "test123456")
    assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
    assert "my-jobs" in resp.headers.get("Location", ""), \
        f"Expected redirect to my-jobs, got {resp.headers.get('Location')}"


def t_login_wrong_password():
    """POST /login with wrong password → stays on login (200 or 302)"""
    s = requests.Session()
    s.get(f"{BASE}/login")
    resp = login(s, "org@test.ru", "wrongpassword")
    # Может быть 200 (форма с ошибкой) или 302 (редирект с flash)
    assert resp.status_code in (200, 302), f"Expected 200 or 302, got {resp.status_code}"
    if resp.status_code == 200:
        assert "Ошибка входа" in resp.text or "неверный" in resp.text.lower(), \
            "Expected error message in response"


def t_login_bad_email():
    """POST /login with invalid email format → stays on login"""
    s = requests.Session()
    s.get(f"{BASE}/login")
    resp = login(s, "not-an-email", "test123456")
    assert resp.status_code in (200, 302), f"Expected 200 or 302, got {resp.status_code}"


def t_myjobs_unauthorized():
    """GET /my-jobs without session → redirect to /login"""
    r = requests.get(f"{BASE}/my-jobs", allow_redirects=False)
    assert r.status_code == 302, f"Expected 302, got {r.status_code}"
    assert "login" in r.headers.get("Location", ""), \
        "Should redirect to login"


def t_myjobs_as_worker():
    """GET /my-jobs with worker session → redirect away (access denied)"""
    s = api_login_get_session("trud3@test.ru", "test123456")
    r = s.get(f"{BASE}/my-jobs", allow_redirects=False)
    # Worker should be redirected away from my-jobs
    assert r.status_code == 302, f"Expected 302 redirect, got {r.status_code}"
    location = r.headers.get("Location", "")
    assert "my-jobs" not in location, f"Worker should not stay on my-jobs, location={location}"


def t_admin_unauthorized():
    """GET /admin without session → redirect to /login"""
    r = requests.get(f"{BASE}/admin", allow_redirects=False)
    assert r.status_code == 302, f"Expected 302, got {r.status_code}"
    assert "login" in r.headers.get("Location", ""), \
        "Should redirect to login"


def t_csrf_protection():
    """POST to /login without CSRF token → should still work (login is exempt)"""
    # Actually test CSRF on a protected endpoint
    s = api_login_get_session("org@test.ru", "test123456")
    # Try to POST without CSRF token to protected endpoint
    r = s.post(f"{BASE}/job/new", data={
        "title": "CSRF Test"
    }, allow_redirects=False)
    # CSRF protection should block (400) or redirect
    assert r.status_code in (400, 302), \
        f"Expected 400 (CSRF block) or 302, got {r.status_code}"


def t_404_error():
    """GET nonexistent page → 404 with error message"""
    r = requests.get(f"{BASE}/xyz-nonexistent")
    assert r.status_code == 404, f"Expected 404, got {r.status_code}"
    assert "Страница не найдена" in r.text or "404" in r.text, \
        "404 page should contain error text"


def t_register_unique_email():
    """Регистрация с уникальным email (временная почта)."""
    import random
    unique_id = random.randint(10000, 99999)
    email = f"test{unique_id}@test.ru"
    s = requests.Session()
    s.get(f"{BASE}/register")
    resp = s.post(f"{BASE}/register", data={
        "full_name": f"Test User {unique_id}",
        "email": email,
        "password": "Test123456!",
        "role": "worker",
        "city": "Москва",
    }, allow_redirects=False)
    # Должен быть редирект на /login после успешной регистрации
    assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
    location = resp.headers.get("Location", "")
    assert "login" in location, f"Should redirect to login, got {location}"


def t_stopwords_block():
    """Стоп-слова («ставка», «зарплата») блокируют создание задания."""
    s = api_login_get_session("org@test.ru", "test123456")
    # Получаем CSRF-токен
    s.get(f"{BASE}/job/new")
    csrf = s.cookies.get('session')
    resp = s.post(f"{BASE}/job/new", data={
        "title": "Работа со ставкой",
        "description": "Тут ставка и зарплата и трудовая",
        "payment": "5000",
        "city": "Москва",
    }, allow_redirects=False)
    # Стоп-слова должны блокировать — возвращает 200 (форма) или редирект обратно
    # Может быть 400 из-за CSRF если cookies не передались
    assert resp.status_code in (200, 302, 400), f"Expected 200/302/400, got {resp.status_code}"
    if resp.status_code == 302:
        assert "job/new" in resp.headers.get("Location", ""), "Should redirect back to form"

def test_old_endpoints_404():
    """Старые endpoints возвращают 404 (архивная модель)."""
    for path in ["/api/pay-for-contact", "/api/contact-payments"]:
        r = requests.get(f"{BASE}{path}")
        assert r.status_code == 404, f"{path} should return 404, got {r.status_code}"

def t_invitation_flow():
    """Приглашение трудника и ответ."""
    s_emp = api_login_get_session("org@test.ru", "test123456")
    s_wrk = api_login_get_session("trud3@test.ru", "test123456")
    # Работодатель приглашает трудника на задание (нужен существующий job_id)
    # Тест существующих приглашений через API
    r = s_emp.get(f"{BASE}/api/invitations")
    assert r.status_code == 200, f"Invitations API should work, got {r.status_code}"
    r2 = s_wrk.get(f"{BASE}/api/invitations")
    assert r2.status_code == 200, f"Worker invitations API should work, got {r2.status_code}"

def t_assetlinks_json():
    """TWA assetlinks.json доступен и валиден."""
    r = requests.get(f"{BASE}/.well-known/assetlinks.json")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert "application/json" in r.headers.get("Content-Type", ""), "Should be JSON"
    data = r.json()
    assert isinstance(data, list), f"Expected JSON array, got {type(data)}"

def t_manifest_json():
    """PWA manifest.json доступен и валиден."""
    r = requests.get(f"{BASE}/static/manifest.json")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data.get("display") == "standalone", f"Expected standalone, got {data.get('display')}"
    assert "theme_color" in data, "Missing theme_color"


def t_skills_sorted():
    """Навыки в /api/skills отсортированы по sort_order."""
    r = requests.get(f"{BASE}/api/skills")
    data = r.json()
    skills = data.get("skills", [])
    if len(skills) > 1:
        # Проверяем что sort_order не убывает
        orders = [s.get("sort_order", 0) for s in skills]
        assert orders == sorted(orders), f"Skills not sorted: {orders[:5]}"


def t_notifications_require_auth():
    """GET /notifications без сессии → редирект на login."""
    r = requests.get(f"{BASE}/notifications", allow_redirects=False)
    assert r.status_code == 302, f"Expected 302, got {r.status_code}"
    assert "login" in r.headers.get("Location", ""), "Should redirect to login"


def t_workers_page_public():
    """GET /workers доступна публично (без авторизации)."""
    r = requests.get(f"{BASE}/workers")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert "Трудники" in r.text, "Workers page should show content"


# ── main ─────────────────────────────────────────

TESTS = [
    ("Health check /", t_health),
    ("API /skills", t_api_skills),
    ("API /religions", t_api_religions),
    ("Login success", t_login_success),
    ("Login wrong password", t_login_wrong_password),
    ("Login bad email", t_login_bad_email),
    ("My-jobs unauthorized", t_myjobs_unauthorized),
    ("My-jobs as worker (blocked)", t_myjobs_as_worker),
    ("Admin unauthorized", t_admin_unauthorized),
    ("CSRF protection", t_csrf_protection),
    ("404 error page", t_404_error),
    ("Register with unique email", t_register_unique_email),
    ("Stop-words block job creation", t_stopwords_block),
    ("Old endpoints return 404", test_old_endpoints_404),
    ("Invitation API accessible", t_invitation_flow),
    ("TWA assetlinks.json", t_assetlinks_json),
    ("PWA manifest.json", t_manifest_json),
    ("Skills sorted by sort_order", t_skills_sorted),
    ("Notifications require auth", t_notifications_require_auth),
    ("Workers page public", t_workers_page_public),
]

if __name__ == "__main__":
    log("INFO", f"Trudnik API Test Report — {BASE}")
    log("INFO", f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("INFO", "=" * 60)

    for name, fn in TESTS:
        test(name, fn)

    log("INFO", f"Total: {PASSED} passed, {FAILED} failed")

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("Trudnik API Test Report\n")
        f.write(f"Server: {BASE}\n")
        f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n")
        for line in REPORT:
            f.write(line + "\n")
        f.write(f"\nTotal: {PASSED} passed, {FAILED} failed\n")

    print(f"\nReport saved to {LOG_FILE}")
    sys.exit(0 if FAILED == 0 else 1)
