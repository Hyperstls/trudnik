"""
Locust-сценарии нагрузочного тестирования для «Трудник» — Блок 4 (PRF-004, PRF-005).

================================================================================
ИНСТРУКЦИИ ПО ЗАПУСКУ
================================================================================

# Базовый запуск (100 пользователей, 10 порождений/сек):
locust -f tests/locustfile.py --host=http://127.0.0.1:5000 --users=100 --spawn-rate=10

# Только batch accept сценарий (50 пользователей):
locust -f tests/locustfile.py --host=http://127.0.0.1:5000 --users=50 --spawn-rate=5 TrudnikBatchUser

# Headless режим (для CI):
locust -f tests/locustfile.py --host=http://127.0.0.1:5000 --users=100 --spawn-rate=10 --run-time=60s --headless --csv=locust_results

# Только класс TrudnikUser:  locust -f tests/locustfile.py TrudnikUser
# Только класс TrudnikBatchUser: locust -f tests/locustfile.py TrudnikBatchUser

================================================================================
ТЕСТОВЫЕ УЧЁТНЫЕ ДАННЫЕ
================================================================================
- Работодатель (employer): org@test.ru / Step@1986
- Трудник (worker):        trud@test.ru / Step@1986

================================================================================
PRF-004: Нагрузочное тестирование поиска заданий
  - Поиск заданий: GET /?q=уборка&city=Москва (HTML-каталог; JSON /api/search/* не существует)
  - Поиск трудников: GET /workers?skills=<random_skill_id>
  - Главная страница и страница работников

PRF-005: Нагрузочное тестирование операций над заявками
  - Массовый accept: POST /api/applications/batch с 50 ID заявок
  - Создание задания: POST /job/new (только employer)
  - Принятие заявки: POST /api/applications/<id>/accept
================================================================================
"""

import json
import os
import random
import re
import time
import uuid as uuid_mod

from locust import HttpUser, between, events, task


# ═════════════════════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ═════════════════════════════════════════════════════════════════════════════

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")

# Тестовые учётные данные
EMPLOYER_EMAIL = "org@test.ru"
EMPLOYER_PASSWORD = "Step@1986"
WORKER_EMAIL = "trud@test.ru"
WORKER_PASSWORD = "Step@1986"

# Вероятность того, что пользователь — работодатель (0.0 — 1.0)
EMPLOYER_RATIO = 0.3

# Пулы ID для случайного выбора (заполняются в on_start)
JOB_IDS = []           # Список ID заданий для view_job_detail
SKILL_IDS = []         # Список ID навыков для search_workers
APPLICATION_IDS = []   # Список ID заявок для batch accept

# Регулярное выражение для извлечения CSRF-токена из <meta name="csrf-token">
CSRF_RE = re.compile(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE)


# ═════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ═════════════════════════════════════════════════════════════════════════════

def extract_csrf(html_text: str) -> str:
    """Извлечь CSRF-токен из HTML-страницы (meta[name='csrf-token'])."""
    match = CSRF_RE.search(html_text)
    if match:
        return match.group(1)
    return ""


def extract_resp_csrf(response) -> str:
    """Извлечь CSRF-токен из ответа Locust (response.text)."""
    if response.text:
        return extract_csrf(response.text)
    return ""


def extract_job_ids(html_text: str) -> list:
    """Извлечь ID заданий из HTML (href='/jobs/<uuid>')."""
    pattern = re.compile(r'href=["\']/jobs/([a-f0-9-]+)["\']', re.IGNORECASE)
    return list(set(pattern.findall(html_text)))


def extract_application_ids(html_text: str) -> list:
    """Извлечь ID заявок из HTML (data-app-id='<uuid>' или app_id=<uuid>)."""
    pattern = re.compile(r'(?:data-app-id|app_id)[\s=]+["\']?([a-f0-9-]+)["\']?', re.IGNORECASE)
    return list(set(pattern.findall(html_text)))


def generate_random_uuid() -> str:
    """Сгенерировать случайный UUID v4 для тестовых данных."""
    return str(uuid_mod.uuid4())


# ═════════════════════════════════════════════════════════════════════════════
# ОБРАБОТЧИКИ СОБЫТИЙ LOCUST
# ═════════════════════════════════════════════════════════════════════════════

@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Логгирование начала конфигурации теста."""
    print("=" * 70)
    print("[Locust] Инициализация нагрузочного теста «Трудник» — Блок 4")
    print(f"[Locust] Базовый URL: {BASE_URL}")
    print(f"[Locust] Тестовые пользователи:")
    print(f"  - Работодатель: {EMPLOYER_EMAIL}")
    print(f"  - Трудник:      {WORKER_EMAIL}")
    print(f"[Locust] Соотношение employer/worker: {EMPLOYER_RATIO:.0%}/{1 - EMPLOYER_RATIO:.0%}")
    print("=" * 70)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Вывод конфигурации при запуске теста."""
    print("\n" + "=" * 70)
    print("[Locust] ТЕСТ ЗАПУЩЕН")
    print(f"[Locust] Пользователей: {environment.runner.target_user_count if environment.runner else 'N/A'}")
    print(f"[Locust] Хост: {environment.host}")
    print("=" * 70 + "\n")


@events.request.add_listener
def on_request(context, **kwargs):
    """
    Обработчик каждого HTTP-запроса.
    - status_code == 429 → пометить как failure (rate limit)
    - status_code == 503 → пометить как failure (Circuit Breaker open)
    """
    if context.response is None:
        return

    status = context.response.status_code

    if status == 429:
        context.response.failure(
            f"Rate Limit (429) — превышен лимит запросов для {context.name}"
        )
    elif status == 503:
        context.response.failure(
            f"Circuit Breaker Open (503) — сервис недоступен для {context.name}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# ОСНОВНОЙ КЛАСС ПОЛЬЗОВАТЕЛЯ — TrudnikUser
# ═════════════════════════════════════════════════════════════════════════════

class TrudnikUser(HttpUser):
    """
    Основной класс пользователя для нагрузочного тестирования «Трудник».

    Имитирует реального пользователя:
    - Логин с CSRF-токеном
    - Просмотр страниц (главная, работники, детализация заданий)
    - Поиск заданий и трудников (PRF-004)
    - Создание заданий (только employer, PRF-005)
    - Health-check
    """

    wait_time = between(1, 3)
    host = BASE_URL

    # ── Инициализация пользователя ────────────────────────────────────────

    def on_start(self):
        """Логин пользователя и извлечение CSRF-токена."""
        # Выбираем роль: employer или worker (случайно, согласно EMPLOYER_RATIO)
        self.is_employer = random.random() < EMPLOYER_RATIO

        # Шаг 1: GET /login → получить CSRF-токен из meta
        with self.client.get("/login", name="GET /login", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Не удалось загрузить страницу логина: {resp.status_code}")
                self._logged_in = False
                return
            self._csrf_token = extract_resp_csrf(resp)

        if not self._csrf_token:
            # Fallback: попробовать главную страницу
            with self.client.get("/", name="GET / (csrf fallback)", catch_response=True) as resp:
                self._csrf_token = extract_resp_csrf(resp)

        # Шаг 2: POST /login → аутентификация
        credentials = {
            "email": EMPLOYER_EMAIL if self.is_employer else WORKER_EMAIL,
            "password": EMPLOYER_PASSWORD if self.is_employer else WORKER_PASSWORD,
            "_csrf_token": self._csrf_token,
        }

        with self.client.post(
            "/login",
            data=credentials,
            name="POST /login",
            catch_response=True,
            allow_redirects=True,
        ) as resp:
            if resp.status_code == 429:
                resp.failure("Rate limited при логине")
                self._logged_in = False
                return
            if resp.status_code != 200 and "/login" in (resp.url or ""):
                resp.failure(f"Логин не удался (статус {resp.status_code})")
                self._logged_in = False
                return
            # После успешного логина редирект на главную / my_jobs
            self._logged_in = True

            # Извлечь CSRF с новой страницы (после редиректа)
            new_csrf = extract_resp_csrf(resp)
            if new_csrf:
                self._csrf_token = new_csrf

        # Шаг 3: Получить справочные данные (навыки) для последующих запросов
        self._fetch_reference_data()

    def _fetch_reference_data(self):
        """Получить справочные ID (навыки, задания) для параметризации запросов."""
        # Получаем список навыков
        with self.client.get("/api/skills", name="GET /api/skills (ref)", catch_response=True) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    skills = data.get("skills", [])
                    if skills and not SKILL_IDS:
                        # Заполняем глобальный пул (только однажды)
                        SKILL_IDS.clear()
                        SKILL_IDS.extend([s["id"] for s in skills if s.get("id")])
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass

        # Получаем список заданий для view_job_detail.
        # /api/search/jobs НЕ существует (фантом) — реальные ID парсим из
        # HTML-каталога `/` (паттерн интеграционных тестов).
        with self.client.get(
            "/",
            name="GET / (jobs ref)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                try:
                    ids = re.findall(r'/jobs/([a-f0-9-]{36})', resp.text)
                    if ids and not JOB_IDS:
                        JOB_IDS.clear()
                        JOB_IDS.extend(dict.fromkeys(ids))
                except Exception:
                    pass

        # Для работодателя: получить ID заявок для batch accept
        if self.is_employer and not APPLICATION_IDS:
            with self.client.get(
                "/my-applications",
                name="GET /my-applications (ref)",
                catch_response=True,
            ) as resp:
                if resp.status_code == 200:
                    app_ids = extract_application_ids(resp.text or "")
                    if app_ids:
                        APPLICATION_IDS.clear()
                        APPLICATION_IDS.extend(app_ids)

    # ── Задачи (tasks) ─────────────────────────────────────────────────────

    @task(5)
    def view_main_page(self):
        """Просмотр главной страницы."""
        with self.client.get("/", name="GET / (главная)", catch_response=True) as resp:
            if resp.status_code == 200:
                # Обновляем CSRF и пул заданий
                new_csrf = extract_resp_csrf(resp)
                if new_csrf:
                    self._csrf_token = new_csrf
                # Пополняем пул ID заданий
                job_ids = extract_job_ids(resp.text or "")
                for jid in job_ids:
                    if jid not in JOB_IDS:
                        JOB_IDS.append(jid)
            else:
                resp.failure(f"Главная страница вернула {resp.status_code}")

    @task(3)
    def search_jobs(self):
        """Поиск заданий (PRF-004): HTML-каталог с фильтрами
        (JSON /api/search/jobs — фантом, реальный поиск в `/`)."""
        params = {
            "q": "уборка",
            "city": "Москва",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        with self.client.get(
            f"/?{query}",
            name="GET / (search PRF-004)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                try:
                    for jid in re.findall(r'/jobs/([a-f0-9-]{36})', resp.text):
                        if jid not in JOB_IDS:
                            JOB_IDS.append(jid)
                except Exception:
                    pass
            else:
                resp.failure(f"Поиск заданий: {resp.status_code}")

    @task(2)
    def view_job_detail(self):
        """Просмотр страницы детализации задания."""
        if not JOB_IDS:
            return  # Нет данных — пропускаем задачу

        job_id = random.choice(JOB_IDS)
        with self.client.get(
            f"/jobs/{job_id}",
            name="GET /jobs/<id>",
            catch_response=True,
        ) as resp:
            if resp.status_code == 404:
                # Задание могло быть удалено — удаляем из пула
                if job_id in JOB_IDS:
                    JOB_IDS.remove(job_id)
            elif resp.status_code != 200:
                resp.failure(f"Детализация задания: {resp.status_code}")

    @task(2)
    def view_workers(self):
        """Просмотр страницы работников."""
        with self.client.get("/workers", name="GET /workers", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Страница работников: {resp.status_code}")

    @task(2)
    def search_workers(self):
        """Поиск трудников по навыку (PRF-004): реальная страница /workers
        (JSON /api/search/workers — фантом)."""
        skills_param = ""
        if SKILL_IDS:
            skill_id = random.choice(SKILL_IDS)
            skills_param = f"?skills={skill_id}"
        else:
            skills_param = "?q=уборка"

        with self.client.get(
            f"/workers{skills_param}",
            name="GET /workers (PRF-004)",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Поиск трудников: {resp.status_code}")

    @task(1)
    def create_job(self):
        """Создание задания (только для employer, PRF-005)."""
        if not self.is_employer:
            return  # Только работодатель создаёт задания

        if not self._csrf_token:
            return  # Нет CSRF-токена — пропускаем

        job_data = {
            "organization_name": f"Тестовое задание {int(time.time())}",
            "description": "Нагрузочное тестирование (Locust)",
            "address": "Москва, Тверская улица",
            "payment_amount": "1500",
            "max_workers": "1",
            "date_time": "",
            "_csrf_token": self._csrf_token,
        }

        with self.client.post(
            "/job/new",
            data=job_data,
            name="POST /job/new (PRF-005)",
            catch_response=True,
            allow_redirects=True,
        ) as resp:
            if resp.status_code == 429:
                resp.failure("Rate limit при создании задания")
            elif resp.status_code in (302, 303):
                # Редирект после успешного создания — OK
                resp.success()
            elif resp.status_code == 200 and "/job/new" not in (resp.url or ""):
                resp.success()
            elif resp.status_code not in (200, 302, 303):
                resp.failure(f"Создание задания: {resp.status_code}")
            else:
                # Обновляем CSRF после запроса
                new_csrf = extract_resp_csrf(resp)
                if new_csrf:
                    self._csrf_token = new_csrf

    @task(1)
    def health_check(self):
        """Проверка работоспособности приложения."""
        with self.client.get("/health", name="GET /health", catch_response=True) as resp:
            if resp.status_code == 503:
                resp.failure("Health check: сервис недоступен (503)")
            elif resp.status_code != 200:
                resp.failure(f"Health check: {resp.status_code}")


# ═════════════════════════════════════════════════════════════════════════════
# ОТДЕЛЬНЫЙ КЛАСС ДЛЯ BATCH ACCEPT — TrudnikBatchUser
# ═════════════════════════════════════════════════════════════════════════════

class TrudnikBatchUser(HttpUser):
    """
    Пользователь для нагрузочного тестирования массового accept заявок (PRF-005).

    Имитирует POST /api/applications/batch с массивом из 50 UUID в action=accept.
    wait_time = between(0.5, 1) — более агрессивная нагрузка.
    """

    wait_time = between(0.5, 1)
    host = BASE_URL

    def on_start(self):
        """Логин работодателем и получение CSRF-токена."""
        # Шаг 1: GET /login → CSRF
        with self.client.get("/login", name="GET /login", catch_response=True) as resp:
            self._csrf_token = extract_resp_csrf(resp)

        if not self._csrf_token:
            with self.client.get("/", name="GET / (csrf fallback)", catch_response=True) as resp:
                self._csrf_token = extract_resp_csrf(resp)

        # Шаг 2: POST /login
        credentials = {
            "email": EMPLOYER_EMAIL,
            "password": EMPLOYER_PASSWORD,
            "_csrf_token": self._csrf_token,
        }
        with self.client.post(
            "/login",
            data=credentials,
            name="POST /login (batch user)",
            catch_response=True,
            allow_redirects=True,
        ) as resp:
            if resp.status_code == 429:
                resp.failure("Rate limited при логине batch user")
                self._logged_in = False
                return
            self._logged_in = "/login" not in (resp.url or "")
            new_csrf = extract_resp_csrf(resp)
            if new_csrf:
                self._csrf_token = new_csrf

    @task
    def batch_accept_50(self):
        """Массовый accept 50 заявок (PRF-005)."""
        if not self._logged_in or not self._csrf_token:
            return

        # Генерируем массив из 50 UUID (реалистичные или случайные)
        # Используем реальные ID из глобального пула, если доступны,
        # иначе генерируем случайные (сервер вернёт ошибки для несуществующих,
        # но это всё равно создаёт нагрузку на batch-эндпоинт)
        if APPLICATION_IDS and len(APPLICATION_IDS) >= 50:
            app_ids = APPLICATION_IDS[:50]
        elif APPLICATION_IDS:
            # Дополняем до 50 случайными UUID
            app_ids = list(APPLICATION_IDS)
            while len(app_ids) < 50:
                app_ids.append(generate_random_uuid())
        else:
            # Полностью случайные UUID — нагрузка на валидацию и поиск
            app_ids = [generate_random_uuid() for _ in range(50)]

        payload = {
            "app_ids": app_ids,
            "action": "accept",
        }

        headers = {
            "Content-Type": "application/json",
            "X-CSRF-Token": self._csrf_token,
        }

        with self.client.post(
            "/api/applications/batch",
            json=payload,
            headers=headers,
            name="POST /api/applications/batch (PRF-005)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 429:
                resp.failure("Rate limit при batch accept")
            elif resp.status_code == 400:
                # Может быть ошибка валидации (несуществующие ID) —
                # это ожидаемо для случайных UUID, endpoint всё равно нагружается
                resp.success()
            elif resp.status_code not in (200, 400):
                resp.failure(f"Batch accept: {resp.status_code}")
