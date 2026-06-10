#!/usr/bin/env python3
"""
Интеграционное тестирование жизненного цикла задания согласно matrix_jobs.md.
Тестирует через HTTP-запросы к запущенному приложению (Flask + Supabase).

Переходы статусов:
  open → in_progress → active → payment_pending → paid → completed

Сценарий:
  1. Работодатель создаёт задание
  2. Трудник откликается
  3. Работодатель принимает отклик → in_progress
  4. Трудник делает чек-ин → active
  5. Трудник завершает смену → payment_pending
  6. Работодатель подтверждает оплату
  7. Трудник подтверждает оплату → paid
  8. Обе стороны оценивают друг друга → completed
"""
import os
import sys
import time
import json
import requests
from datetime import datetime

# ── Конфигурация ────────────────────────────────────────
BASE = os.environ.get('TRUDNIK_BASE', 'http://127.0.0.1:5000').rstrip('/')
E_EMAIL = os.environ.get('TRUDNIK_EMPLOYER_EMAIL')
E_PASS = os.environ.get('TRUDNIK_EMPLOYER_PASS')
W_EMAIL = os.environ.get('TRUDNIK_WORKER_EMAIL')
W_PASS = os.environ.get('TRUDNIK_WORKER_PASS')

# Проверка обязательных переменных окружения
_missing = [v for v in ['TRUDNIK_EMPLOYER_EMAIL', 'TRUDNIK_EMPLOYER_PASS',
                         'TRUDNIK_WORKER_EMAIL', 'TRUDNIK_WORKER_PASS']
            if not os.environ.get(v)]
if _missing:
    print(f"ERROR: Missing environment variables: {', '.join(_missing)}")
    print("Set them before running this test, e.g.:")
    print("  export TRUDNIK_EMPLOYER_EMAIL=org@test.ru")
    sys.exit(1)

results = []
def rep(name, passed, detail=""):
    s = "PASS" if passed else "FAIL"
    m = "[%s] %s | %s" % (datetime.now().strftime('%H:%M:%S'), s, name)
    if detail:
        m += " -- " + str(detail)
    results.append(m)
    print(m)


class TesterSession:
    """Обёртка сессии с cookie-авторизацией через Flask."""
    def __init__(self, role_name):
        self.s = requests.Session()
        self.role = role_name
        self.csrf = ""

    def login(self, email, password):
        # Сначала получаем страницу логина для CSRF
        r = self.s.get(BASE + "/login")
        self._extract_csrf(r.text)

        if "/login" not in r.url:
            rep(f"{self.role} login (already)", True)
            return True

        # POST с CSRF-токеном и email/password
        data = {
            "email": email,
            "password": password,
            "_csrf_token": self.csrf,
        }
        r = self.s.post(BASE + "/login", data=data, allow_redirects=True)
        ok = "/login" not in r.url
        rep(f"{self.role} login", ok, f"status={r.status_code}" if not ok else "")
        self._extract_csrf(r.text)
        return ok

    def _extract_csrf(self, html):
        import re
        m = re.search(r'name="_csrf_token"[^>]*value="([^"]+)"', html)
        if not m:
            m = re.search(r'csrf_token.*?value="([^"]+)"', html)
        if m:
            self.csrf = m.group(1)

    def _get_csrf(self):
        r = self.s.get(BASE + "/")
        self._extract_csrf(r.text)

    def get(self, path, **kw):
        return self.s.get(BASE + path, **kw)

    def post(self, path, data=None, json_data=None, **kw):
        h = {}
        if self.csrf:
            h['X-CSRF-Token'] = self.csrf
        if json_data:
            h['Content-Type'] = 'application/json'
            r = self.s.post(BASE + path, json=json_data, headers=h, **kw)
        else:
            data = data or {}
            r = self.s.post(BASE + path, data=data, headers=h, **kw)
        # Extract CSRF from redirect response if present
        self._extract_csrf(r.text)
        return r


# ── Создание сессий ──────────────────────────────────────
employer = TesterSession("employer")
worker = TesterSession("worker")


def test_full_lifecycle():
    job_id = None
    app_id = None
    shift_id = None

    # 1. Авторизация
    if not employer.login(E_EMAIL, E_PASS):
        return False
    if not worker.login(W_EMAIL, W_PASS):
        return False

    time.sleep(1)

    # 2. Работодатель создаёт задание
    r = employer.get("/job/new")
    rep("employer open /job/new", "/job/new" in r.url)

    r = employer.post("/job/new", data={
        "title": "TEST Kitchen " + datetime.now().strftime('%H%M%S'),
        "description": "Test job for lifecycle testing",
        "payment": "2000",
        "address": "Москва, ул. Тестовая",
        "city": "Москва",
        "max_workers": "1",
        "work_type": "",
        "latitude": "55.75",
        "longitude": "37.61",
        "preferred_religion": "",
    })
    rep("employer create job", "/my-jobs" in r.url, r.url[:80])

    # Получить ID созданного задания
    r = employer.get("/my-jobs")
    import re
    matches = re.findall(r'/jobs/([a-f0-9-]{36})', r.text)
    if matches:
        # Берём первое попавшееся новое задание (последнее созданное)
        job_ids = list(set(matches))
        for jid in job_ids:
            jr = employer.get(f"/jobs/{jid}")
            if "TEST Kitchen" in jr.text:
                job_id = jid
                break
    rep("employer find job ID", job_id is not None, str(job_id)[:20] if job_id else "")

    if not job_id:
        return False

    time.sleep(1)

    # 3. Проверить статус задания = open
    r = employer.get(f"/jobs/{job_id}")
    rep("job status open", "Открыто" in r.text, "status=open?")

    # 4. Трудник откликается
    r = worker.get("/")
    rep("worker see jobs page", "/" in r.url or "/jobs" in r.url)

    r = worker.post(f"/apply/{job_id}")
    rep("worker apply", "/jobs" in r.url or "/" in r.url, r.url[:80])

    time.sleep(1)

    # 5. Проверить отклик на стороне работодателя
    r = employer.get("/my-applications")
    rep("employer see applications", r.status_code == 200)

    # Найти ID отклика
    app_matches = re.findall(r'/api/applications/([a-f0-9-]{36})', r.text)
    # Или через accept кнопки
    accept_matches = re.findall(r'data-app-id="([a-f0-9-]{36})"', r.text)
    if accept_matches:
        app_id = accept_matches[0]
    rep("employer find application ID", app_id is not None, app_id[:20] if app_id else "")

    if not app_id:
        rep("employer find application ID (fallback)", False, "Cannot find application")
        return False

    # 6. Работодатель принимает отклик
    r = employer.post(
        f"/api/applications/{app_id}/accept",
        json_data={},
    )
    r_json = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
    rep("employer accept application", r_json.get('success', False), r.text[:200])

    # Получить shift_id из ответа
    shift_id = r_json.get('shift_id')
    if not shift_id:
        # Попробуем найти через shifts
        r = worker.get("/shifts")
        shift_matches = re.findall(r'shift_id[=]([a-f0-9-]{36})', r.text)
        if shift_matches:
            shift_id = shift_matches[0]

    rep("shift_id from accept", shift_id is not None, str(shift_id)[:20] if shift_id else "")

    time.sleep(1)

    # 7. Проверить статус задания = in_progress
    r = employer.get(f"/jobs/{job_id}")
    rep("job status in_progress", "В работе" in r.text or "in_progress" in r.text)

    # 8. Трудник делает чек-ин
    if not shift_id:
        rep("shift_id missing, cannot proceed", False)
        return False

    r = worker.post(f"/shift/{shift_id}/checkin")
    rep("worker checkin", r.status_code == 200, r.url[:80])

    time.sleep(1)

    # 9. Проверить статус задания = active
    r = employer.get(f"/jobs/{job_id}")
    rep("job status active", "Активно" in r.text or "active" in r.text.lower())

    # 10. Трудник завершает смену
    r = worker.post(f"/shift/{shift_id}/complete")
    rep("worker complete shift", r.status_code == 200, r.url[:80])

    time.sleep(1)

    # 11. Проверить статус = payment_pending
    r = employer.get(f"/jobs/{job_id}")
    rep("job status payment_pending", "Ожидает оплаты" in r.text or "payment_pending" in r.text.lower(),
        "text: " + r.text[200:600] if "Ожидает" not in r.text else "")

    # 12. Работодатель подтверждает оплату
    r = employer.post(f"/shift/{shift_id}/confirm-payment", data={
        "action": "confirm_employer"
    })
    rep("employer confirm payment", r.status_code == 200, r.url[:80])

    time.sleep(1)

    # 13. Трудник подтверждает оплату
    r = worker.post(f"/shift/{shift_id}/confirm-payment", data={
        "action": "confirm_worker"
    })
    rep("worker confirm payment", r.status_code == 200, r.url[:80])

    time.sleep(1)

    # 14. Проверить статус = paid
    r = employer.get(f"/jobs/{job_id}")
    rep("job status paid", "Оплачено" in r.text or "paid" in r.text.lower(),
        "text: " + r.text[200:600] if "Оплачено" not in r.text else "")

    # 15. Оценить друг друга
    # Работодатель оценивает трудника
    # Сначала найдём worker_id через страницу смен
    worker_id = None
    r = worker.get("/shifts")
    w_matches = re.findall(r'data-worker-id="([a-f0-9-]{36})"', r.text)
    if not w_matches:
        w_matches = re.findall(r'worker_id[=]([a-f0-9-]{36})', r.text)
    if w_matches:
        worker_id = w_matches[0]

    if not worker_id:
        # Fallback: извлечь из данных задания
        j_r = employer.get(f"/jobs/{job_id}")
        w_fallback = re.findall(r'data-worker-id="([a-f0-9-]{36})"', j_r.text)
        if w_fallback:
            worker_id = w_fallback[0]

    if not worker_id:
        rep("cannot find worker_id for rating", False)
        return False

    rep("found worker_id", True, worker_id[:20])

    r = employer.post("/api/ratings", json_data={
        "job_id": job_id,
        "rated_user_id": worker_id,
        "rating": 5,
        "comment": "Отличный работник!",
        "target_type": "worker",
    })
    e_rating = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
    rep("employer rate worker", e_rating.get('success', False), str(e_rating)[:200])

    time.sleep(1)

    # Трудник оценивает работодателя
    # Извлекаем employer_id из страницы задания (надёжнее, чем cookies)
    employer_id = None
    j_r = worker.get(f"/jobs/{job_id}")
    e_matches = re.findall(r'employer_id["\s:]+([a-f0-9-]{36})', j_r.text)
    if not e_matches:
        # Альтернативный паттерн: data-employer-id
        e_matches = re.findall(r'data-employer-id="([a-f0-9-]{36})"', j_r.text)
    if e_matches:
        employer_id = e_matches[0]

    if not employer_id:
        rep("cannot find employer_id for rating", False)
        return False

    rep("found employer_id", True, employer_id[:20])

    r = worker.post("/api/ratings", json_data={
        "job_id": job_id,
        "rated_user_id": employer_id,
        "rating": 4,
        "comment": "Хороший работодатель",
        "target_type": "employer",
    })
    w_rating = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
    rep("worker rate employer", w_rating.get('success', False), str(w_rating)[:200])

    time.sleep(1)

    # 16. Проверить статус = completed
    r = employer.get(f"/jobs/{job_id}")
    rep("job status completed", "Завершено" in r.text or "completed" in r.text.lower(),
        "text: " + r.text[200:600] if "Завершено" not in r.text else "")

    # 17. Проверить отображение оценок на странице задания
    r = employer.get(f"/jobs/{job_id}")
    rep("ratings visible on job page", "★" in r.text or "Отзывы" in r.text,
        "Found ratings section" if "★" in r.text else "Ratings NOT found")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Job Lifecycle Test - matrix_jobs.md compliance")
    print("Server:", BASE)
    print("=" * 60)

    ok = test_full_lifecycle()

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if "PASS" in r)
    failed = sum(1 for r in results if "FAIL" in r)
    print(f"Results: {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 60)

    sys.exit(0 if not failed else 1)
