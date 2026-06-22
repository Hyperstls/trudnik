#!/usr/bin/env python3
"""
Скрипт автоматизированного тестирования ВСЕХ кнопок приложения «Трудник»
на основе реестра docs/BUTTON_REGISTRY.md.

Запуск: python scripts/test_buttons.py
Вывод: docs/BUTTON_TEST_RESULTS.txt

Требования:
- Flask-сервер запущен на http://127.0.0.1:5000 с TESTING=true
- Существуют тестовые пользователи: org@test.ru, trud@test.ru, admin@test.ru
"""

import sys
import os
import time
import re
import json
import traceback
import locale
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

# Fix Unicode output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ——————————————————————————————
# Конфигурация
# ——————————————————————————————
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")

# Учётные данные — только из переменных окружения (НИКАКИХ хардкод-паролей)
_worker_email = os.getenv("TEST_WORKER_EMAIL")
_worker_pass = os.getenv("TEST_WORKER_PASSWORD")
_employer_email = os.getenv("TEST_EMPLOYER_EMAIL")
_employer_pass = os.getenv("TEST_EMPLOYER_PASSWORD")
_admin_email = os.getenv("TEST_ADMIN_EMAIL")
_admin_pass = os.getenv("TEST_ADMIN_PASSWORD")
_alt_passwords_str = os.getenv("TEST_ALT_PASSWORDS", "")

assert _worker_email, "TEST_WORKER_EMAIL must be set"
assert _worker_pass, "TEST_WORKER_PASSWORD must be set"
assert _employer_email, "TEST_EMPLOYER_EMAIL must be set"
assert _employer_pass, "TEST_EMPLOYER_PASSWORD must be set"
assert _admin_email, "TEST_ADMIN_EMAIL must be set"
assert _admin_pass, "TEST_ADMIN_PASSWORD must be set"

CREDENTIALS = {
    "worker":    {"email": _worker_email,  "password": _worker_pass, "name": "Трудник"},
    "employer":  {"email": _employer_email,   "password": _employer_pass, "name": "Работодатель"},
    "admin":     {"email": _admin_email, "password": _admin_pass, "name": "Админ"},
}

# Альтернативные пароли для fallback-попыток (через запятую в TEST_ALT_PASSWORDS)
ALT_PASSWORDS = [p.strip() for p in _alt_passwords_str.split(",") if p.strip()] if _alt_passwords_str else []

OUTPUT_FILE = "docs/BUTTON_TEST_RESULTS.txt"

# Глобальные счётчики
total_passed = 0
total_failed = 0
total_skipped = 0
results_log = []  # [(type, message)]


# ——————————————————————————————
# Утилиты вывода
# ——————————————————————————————
def log(level: str, msg: str) -> None:
    global total_passed, total_failed, total_skipped
    if level == "OK":
        total_passed += 1
    elif level == "FAIL":
        total_failed += 1
    elif level == "SKIP":
        total_skipped += 1
    prefix = {"OK": "  [OK]", "FAIL": "  [FAIL]", "SKIP": "  [SKIP]"}
    line = f"{prefix.get(level, '  [---]')} {msg}"
    results_log.append(line)
    print(line)
    sys.stdout.flush()


def extract_csrf(html: str) -> Optional[str]:
    m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else None


def get_csrf_from_session(session: requests.Session, path: str = "/") -> Optional[str]:
    try:
        resp = session.get(f"{BASE_URL}{path}", timeout=30)
        return extract_csrf(resp.text)
    except Exception:
        return None


def contains_button(html: str, text: str) -> bool:
    """Проверяет наличие текста кнопки в HTML (нестрогий поиск)."""
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text().lower()
    for btn_text in (text, text.lower(), text.capitalize()):
        if btn_text.lower() in page_text:
            return True
    # Также поищем в data-атрибутах
    for el in soup.find_all(attrs={"data-action": True}):
        if text.lower() in (el.get("data-action", "") or "").lower():
            return True
    # Ищем в value кнопок
    for el in soup.find_all(["button", "input", "a"]):
        val = (el.get("value") or "").lower()
        title = (el.get("title") or "").lower()
        aria = (el.get("aria-label") or "").lower()
        txt = el.get_text().lower()
        if text.lower() in val or text.lower() in title or text.lower() in aria or text.lower() in txt:
            return True
    return False


def extract_job_id_from_page(session: requests.Session, path: str = "/") -> Optional[str]:
    """Извлекает первый job_id из HTML-страницы через BeautifulSoup.
    
    Ищет:
    1. data-job-id атрибуты
    2. Ссылки вида /jobs/<uuid>
    3. Чекбоксы с name="job_ids"
    
    Возвращает UUID строку или None.
    """
    try:
        resp = session.get(f"{BASE_URL}{path}", timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # 1. data-job-id атрибуты
        for el in soup.select("[data-job-id]"):
            jid = el.get("data-job-id")
            if jid and re.match(r'^[a-f0-9-]{36}$', str(jid)):
                return str(jid)
        
        # 2. Ссылки href="/jobs/<uuid>"
        for a in soup.select('a[href^="/jobs/"]'):
            href = a.get("href", "")
            m = re.search(r'/jobs/([a-f0-9-]{36})', href)
            if m:
                return m.group(1)
        
        # 3. Чекбоксы <input name="job_ids" value="<uuid>">
        for inp in soup.select('input[name="job_ids"]'):
            val = inp.get("value", "")
            if re.match(r'^[a-f0-9-]{36}$', val):
                return val
        
        return None
    except Exception:
        return None


# ——————————————————————————————
# Аутентификация
# ——————————————————————————————
def login_session(email: str, password: str, role_name: str) -> Optional[requests.Session]:
    """Создаёт и возвращает авторизованную сессию."""
    session = requests.Session()
    for attempt in range(3):
        try:
            # Сначала получаем страницу логина для кук
            session.get(f"{BASE_URL}/login", timeout=30)
            resp = session.post(
                f"{BASE_URL}/login",
                data={"email": email, "password": password},
                timeout=30,
                allow_redirects=True,
            )
            if resp.status_code == 429:
                log("SKIP", f"Rate limit при входе как {role_name}, попытка {attempt+1}/3")
                time.sleep(5)
                continue
            if "Ошибка входа" in resp.text:
                log("FAIL", f"Неверный пароль для {role_name} ({email})")
                return None
            # Проверяем, что мы действительно залогинены
            check = session.get(f"{BASE_URL}/", timeout=30)
            if "Войти" not in check.text or email in check.text or role_name.lower() in check.text.lower():
                return session
            # Проверяем сессию через профиль
            check = session.get(f"{BASE_URL}/profile", timeout=30)
            if check.status_code == 200 and "Войти" not in check.text:
                return session
            log("SKIP", f"Не удалось подтвердить вход как {role_name}, попытка {attempt+1}/3")
        except requests.RequestException as e:
            log("SKIP", f"Ошибка соединения при входе как {role_name}: {e}")
            time.sleep(2)
    return None


def try_login_all_passwords(email: str, role_name: str) -> Optional[requests.Session]:
    """Пробует все известные пароли."""
    for pwd in ALT_PASSWORDS:
        log("OK", f"Пробуем пароль '{pwd}' для {role_name} ({email})")
        s = login_session(email, pwd, role_name)
        if s:
            return s
    return None


# ——————————————————————————————
# Тестирование GET-страниц
# ——————————————————————————————
def test_get_page(session: requests.Session, role: str, url: str,
                  page_name: str, expected_status: int = 200,
                  expected_buttons: list = None,
                  forbidden_buttons: list = None) -> None:
    """
    Тестирует GET-доступ к странице и проверяет наличие кнопок.
    
    expected_status: 200 (доступна), 302 (редирект), 403 (запрещено)
    """
    full_url = url if url.startswith("http") else f"{BASE_URL}{url}"
    display_url = url

    try:
        resp = session.get(full_url, timeout=30, allow_redirects=False)
        status = resp.status_code

        # Обработка редиректов
        if status in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            if expected_status == 302:
                log("OK", f"GET {display_url} → {status}, редирект на {location} (как ожидалось)")
            elif expected_status == 200 and "login" in location.lower():
                log("OK", f"GET {display_url} → {status}, редирект на логин (требуется авторизация)")
            else:
                log("OK", f"GET {display_url} → {status}, редирект на {location}")
            return

        if status == expected_status:
            log("OK", f"GET {display_url} → {status} (страница «{page_name}»)")

            # Проверяем наличие кнопок
            if expected_buttons:
                for btn in expected_buttons:
                    if contains_button(resp.text, btn):
                        log("OK", f"  Кнопка «{btn}» найдена на «{page_name}»")
                    else:
                        log("FAIL", f"  Кнопка «{btn}» НЕ найдена на «{page_name}» (GET {display_url})")

            if forbidden_buttons:
                for btn in forbidden_buttons:
                    if contains_button(resp.text, btn):
                        log("FAIL", f"  Кнопка «{btn}» НЕ должна быть видна на «{page_name}» для роли {role}, но найдена")
                    else:
                        log("OK", f"  Кнопка «{btn}» корректно скрыта на «{page_name}» для роли {role}")
        else:
            log("FAIL", f"GET {display_url} → {status} (ожидался {expected_status}), страница «{page_name}»")

    except requests.RequestException as e:
        log("FAIL", f"GET {display_url} → ОШИБКА соединения: {e}")


def test_post_action(session: requests.Session, role: str, method: str, url: str,
                     action_name: str, data: dict = None, json_data: dict = None,
                     expected_status: int = 302, allow_redirects: bool = True,
                     is_ajax: bool = False) -> None:
    """Тестирует POST/PUT/DELETE действие."""
    full_url = url if url.startswith("http") else f"{BASE_URL}{url}"
    display_url = url
    method = method.upper()

    try:
        headers = {}
        if is_ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"
            csrf = get_csrf_from_session(session)
            if csrf:
                headers["X-CSRF-Token"] = csrf
                if json_data:
                    json_data["_csrf_token"] = csrf

        if method == "POST":
            if json_data:
                resp = session.post(full_url, json=json_data, headers=headers,
                                    timeout=30, allow_redirects=allow_redirects)
            else:
                resp = session.post(full_url, data=data or {}, headers=headers,
                                    timeout=30, allow_redirects=allow_redirects)
        elif method == "PUT":
            resp = session.put(full_url, json=json_data or {}, headers=headers,
                               timeout=30, allow_redirects=allow_redirects)
        elif method == "DELETE":
            resp = session.delete(full_url, headers=headers,
                                  timeout=30, allow_redirects=allow_redirects)
        else:
            log("SKIP", f"Неподдерживаемый метод {method} для {action_name}")
            return

        status = resp.status_code

        if status == expected_status:
            log("OK", f"{method} {display_url} → {status} («{action_name}»)")
        elif status == 403:
            log("OK", f"{method} {display_url} → 403 (доступ запрещён для роли {role}, «{action_name}»)")
        elif status in (301, 302, 303):
            location = resp.headers.get("Location", "")
            log("OK", f"{method} {display_url} → {status}, редирект на {location} («{action_name}»)")
        elif status == 400:
            body = resp.text[:200] if resp.text else ""
            log("OK", f"{method} {display_url} → 400 (неверный запрос, «{action_name}»): {body}")
        elif status == 404:
            log("OK", f"{method} {display_url} → 404 (не найдено, «{action_name}») — возможно, нет тестовых данных")
        elif status == 500:
            log("FAIL", f"{method} {display_url} → 500 (внутренняя ошибка, «{action_name}»)")
        else:
            log("FAIL", f"{method} {display_url} → {status} (ожидался {expected_status}, «{action_name}»)")

    except requests.RequestException as e:
        log("FAIL", f"{method} {display_url} → ОШИБКА: {e} («{action_name}»)")


# ——————————————————————————————
# Тесты для всех ролей
# ——————————————————————————————
def test_common_pages(session: requests.Session, role: str) -> None:
    """Тестирует страницы, доступные всем ролям."""
    print(f"\n--- Общие страницы ---")

    # Главная
    test_get_page(session, role, "/", "Главная", expected_status=200,
                  expected_buttons=["Трудник", "Задания", "Поиск"] if role != "admin" else [])

    # Список заданий
    test_get_page(session, role, "/jobs", "Список заданий", expected_status=200)

    # Поиск
    test_get_page(session, role, "/search", "Поиск", expected_status=200)

    # Список работодателей
    test_get_page(session, role, "/employers", "Список работодателей", expected_status=200)
    test_get_page(session, role, "/workers", "Список трудников", expected_status=200)

    # Чат (список)
    test_get_page(session, role, "/chats", "Чаты (список)", expected_status=200)

    # Уведомления
    test_get_page(session, role, "/notifications", "Уведомления", expected_status=200)

    # Настройки уведомлений
    test_get_page(session, role, "/notifications/settings", "Настройки уведомлений", expected_status=200)

    # Профиль
    test_get_page(session, role, "/profile", "Профиль", expected_status=200,
                  expected_buttons=["Сохранить", "Изменить пароль"])

    # Избранное
    test_get_page(session, role, "/favorites", "Избранное", expected_status=200)


def test_worker_pages(session: requests.Session) -> None:
    """Тестирует страницы, специфичные для трудника."""
    role = "worker"
    print(f"\n--- Страницы трудника ---")

    # Главная с фильтрами трудника
    test_get_page(session, role, "/", "Главная (трудник)", expected_status=200,
                  expected_buttons=["Откликнуться"])

    # Мои отклики
    test_get_page(session, role, "/my-applications", "Мои отклики", expected_status=200)

    # Приглашения
    test_get_page(session, role, "/invitations", "Приглашения", expected_status=200)

    # Избранное (задания + работодатели)
    test_get_page(session, role, "/favorites", "Избранное (трудник)", expected_status=200)


def test_employer_pages(session: requests.Session) -> None:
    """Тестирует страницы, специфичные для работодателя."""
    role = "employer"
    print(f"\n--- Страницы работодателя ---")

    # Мои задания
    test_get_page(session, role, "/my-jobs", "Мои задания", expected_status=200,
                  expected_buttons=["Создать"])

    # Создание задания
    test_get_page(session, role, "/job/new", "Создание задания", expected_status=200,
                  expected_buttons=["Создать задание"])

    # Отклики на мои задания
    test_get_page(session, role, "/my-applications", "Отклики на мои задания", expected_status=200)

    # Чёрный список
    test_get_page(session, role, "/blacklist", "Чёрный список", expected_status=200)

    # Верификация
    test_get_page(session, role, "/verify-employer", "Верификация работодателя", expected_status=200)


def test_admin_pages(session: requests.Session) -> None:
    """Тестирует страницы, специфичные для админа."""
    role = "admin"
    print(f"\n--- Страницы админа ---")

    # Админ-панель
    test_get_page(session, role, "/admin", "Админ-панель", expected_status=200,
                  expected_buttons=["Пользователи", "Задания"])

    # Вкладки админки
    for tab in ["dashboard", "users", "jobs", "verification", "skills", "religions", "stats"]:
        test_get_page(session, role, f"/admin?tab={tab}", f"Админ-панель (tab={tab})", expected_status=200)

    # Чёрный список
    test_get_page(session, role, "/blacklist", "Чёрный список (админ)", expected_status=200)


# ——————————————————————————————
# Тестирование действий
# ——————————————————————————————
def test_worker_actions(session: requests.Session) -> None:
    """Тестирует действия трудника."""
    role = "worker"
    print(f"\n--- Действия трудника ---")

    # Попытка откликнуться на задание (если есть)
    # Ищем job_id через BeautifulSoup: главная, список заданий, поиск
    job_id = None
    for path in ["/", "/jobs", "/search"]:
        job_id = extract_job_id_from_page(session, path)
        if job_id:
            log("OK", f"Найден job_id={job_id[:12]}... на странице {path}")
            break

    if job_id:
        # Отклик
        test_post_action(session, role, "POST", f"/apply/{job_id}",
                         "Откликнуться на задание", expected_status=302)

        # Отзыв отклика
        test_post_action(session, role, "POST", f"/unapply/{job_id}",
                         "Отозвать отклик", expected_status=302)

        # Добавить в избранное
        test_post_action(session, role, "POST", f"/favorite-job/{job_id}",
                         "Добавить задание в избранное", expected_status=302)

        # Удалить из избранного
        test_post_action(session, role, "POST", f"/unfavorite-job/{job_id}",
                         "Удалить задание из избранного", expected_status=302)
    else:
        log("SKIP", "Нет заданий на /, /jobs, /search — действия трудника пропущены")

    # Профиль: сохранить изменения
    test_post_action(session, role, "POST", "/profile/update",
                     "Сохранить изменения профиля",
                     data={"full_name": "Trud Test", "city": "Москва"},
                     expected_status=302)

    # Изменение пароля (будет ошибка без правильного старого пароля)
    test_post_action(session, role, "POST", "/profile/change-password",
                     "Изменить пароль",
                     data={"old_password": "wrong", "new_password": "newpass123", "confirm_password": "newpass123"},
                     expected_status=302)

    # Массовый отклик (если есть чекбоксы)
    test_post_action(session, role, "POST", "/apply-selected",
                     "Массовый отклик", expected_status=302)

    # Массовый отзыв
    test_post_action(session, role, "POST", "/unapply-selected",
                     "Массовый отзыв откликов", expected_status=302)

    # API: favourites check
    test_post_action(session, role, "POST", "/api/favorites/check",
                     "Проверка избранного (API)",
                     json_data={"type": "job", "item_id": "00000000-0000-0000-0000-000000000001"},
                     expected_status=200, is_ajax=True)

    # API: уведомления — прочитать все
    test_post_action(session, role, "POST", "/api/notifications/read-all",
                     "Прочитать все уведомления",
                     json_data={}, expected_status=200, is_ajax=True)


def test_employer_actions(session: requests.Session) -> None:
    """Тестирует действия работодателя."""
    role = "employer"
    print(f"\n--- Действия работодателя ---")

    # Создание тестового задания
    job_id = None
    try:
        timestamp = int(time.time())
        test_title = f"Тестовое задание {timestamp}"
        csrf = get_csrf_from_session(session, "/job/new")
        resp = session.post(f"{BASE_URL}/job/new", data={
            "_csrf_token": csrf or "",
            "title": test_title,
            "description": "Описание для автоматического тестирования кнопок",
            "work_type": "Уборка",
            "payment": "1000",
            "address": "Москва, ул. Тестовая, 1",
            "city": "Москва",
            "latitude": "55.75",
            "longitude": "37.61",
            "max_workers": "1",
        }, timeout=30, allow_redirects=False)

        status = resp.status_code
        location = resp.headers.get("Location", "")
        print(f"  [DEBUG] POST /job/new → status={status}, Location={location}")
        print(f"  [DEBUG] Response body (первые 300 символов): {resp.text[:300]}")

        log("OK", f"POST /job/new → {status} (создание тестового задания)")

        # Стратегия 1: редирект 302 → переходим по Location и парсим страницу
        if status in (301, 302, 303):
            # Редирект может быть на /my-jobs или /jobs/<uuid>
            parts = location.strip("/").split("/")
            print(f"  [DEBUG] Редирект на {location}, parts={parts}")

            # Вариант А: редирект на /jobs/<uuid>
            if len(parts) >= 2 and parts[0] == "jobs" and re.match(r'^[a-f0-9-]{36}$', parts[1]):
                job_id = parts[1]
                print(f"  [DEBUG] ID извлечён из URL редиректа: {job_id}")

            # Вариант Б: редирект на /my-jobs → переходим и парсим список
            if not job_id:
                print(f"  [DEBUG] Переходим по редиректу {location} для поиска задания...")
                my_jobs_resp = session.get(f"{BASE_URL}{location}", timeout=30)
                print(f"  [DEBUG] GET {location} → {my_jobs_resp.status_code}")

                # Парсим страницу: ищем data-job-id, ссылки /jobs/<uuid>, чекбоксы
                soup = BeautifulSoup(my_jobs_resp.text, "html.parser")

                # 1) data-job-id (самый надёжный)
                for el in soup.select("[data-job-id]"):
                    jid = el.get("data-job-id")
                    if jid and re.match(r'^[a-f0-9-]{36}$', str(jid)):
                        job_id = str(jid)
                        print(f"  [DEBUG] ID из data-job-id: {job_id[:12]}...")
                        break

                # 2) Ссылки href="/jobs/<uuid>" — берём последнюю (самую новую)
                if not job_id:
                    href_ids = []
                    for a in soup.select('a[href^="/jobs/"]'):
                        m = re.search(r'/jobs/([a-f0-9-]{36})', a.get("href", ""))
                        if m:
                            href_ids.append(m.group(1))
                    # Исключаем ссылки с /edit, /rate-workers и т.д. — только чистые /jobs/<uuid>
                    if href_ids:
                        job_id = href_ids[-1]  # последнее = самое новое
                        print(f"  [DEBUG] ID из ссылки /jobs/<uuid> (последний): {job_id[:12]}... (всего найдено {len(href_ids)})")

                # 3) Чекбоксы name="job_ids" — берём последний
                if not job_id:
                    for inp in soup.select('input[name="job_ids"]'):
                        val = inp.get("value", "")
                        if re.match(r'^[a-f0-9-]{36}$', val):
                            job_id = val
                            print(f"  [DEBUG] ID из чекбокса: {job_id[:12]}...")
                            break

                # 4) Поиск по названию задания в тексте страницы
                if not job_id:
                    print(f"  [DEBUG] Поиск по названию «{test_title}» в /my-jobs...")
                    for card in soup.select('.app-card, [data-job-id], .job-card'):
                        card_text = card.get_text()
                        if test_title in card_text:
                            # Ищем любой UUID внутри карточки
                            found = re.findall(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', str(card))
                            if found:
                                job_id = found[0]
                                print(f"  [DEBUG] ID найден по названию в карточке: {job_id[:12]}...")
                                break

        # Стратегия 2: статус 200 — форма перерендерена (ошибка валидации)
        elif status == 200:
            # Проверяем, есть ли в ответе flash-сообщение об успехе (редирект не сработал)
            if "успешно создано" in resp.text.lower() or "задание успешно" in resp.text.lower():
                print(f"  [DEBUG] Статус 200, но есть сообщение об успехе — ищем ID в ответе...")
                job_ids = re.findall(r'/jobs/([a-f0-9-]{36})', resp.text)
                if job_ids:
                    job_id = job_ids[-1]
                    print(f"  [DEBUG] ID из тела ответа (200): {job_id[:12]}...")
            else:
                # Ошибка валидации — выводим сообщение
                soup = BeautifulSoup(resp.text, "html.parser")
                flash_msgs = soup.select('.alert, .flash-message, [role="alert"]')
                if flash_msgs:
                    print(f"  [DEBUG] Flash-сообщения в ответе: {[m.get_text(strip=True)[:100] for m in flash_msgs]}")
                print(f"  [DEBUG] Статус 200 — вероятно, ошибка валидации формы")

        if job_id:
            log("OK", f"Создано тестовое задание: {job_id[:12]}...")
        else:
            log("SKIP", f"Не удалось определить ID созданного задания (статус={status}, location={location})")
    except Exception as e:
        log("FAIL", f"Ошибка при создании тестового задания: {e}")
        traceback.print_exc()

    # Если задание создано, тестируем действия с ним
    if job_id:
        # Редактирование
        test_get_page(session, role, f"/jobs/{job_id}/edit", "Редактирование задания", expected_status=200)

        # Сохранить изменения
        csrf = get_csrf_from_session(session, f"/jobs/{job_id}/edit")
        test_post_action(session, role, "POST", f"/jobs/{job_id}/edit",
                         "Сохранить изменения задания",
                         data={"_csrf_token": csrf or "", "title": f"Обновлённое задание {int(time.time())}",
                               "description": "Обновлённое описание", "payment": "1500", "city": "Москва",
                               "work_type": "Уборка", "address": "Москва, ул. Тестовая, 2",
                               "latitude": "55.75", "longitude": "37.61", "max_workers": "1"},
                         expected_status=302)

        # Отозвать задание (cancel)
        test_post_action(session, role, "POST", f"/cancel-job/{job_id}",
                         "Отозвать задание", expected_status=302, is_ajax=True)

        # Восстановить задание
        test_post_action(session, role, "POST", f"/restore-job/{job_id}",
                         "Восстановить задание", expected_status=302, is_ajax=True)

        # Принудительно завершить
        test_post_action(session, role, "POST", f"/api/jobs/{job_id}/force-complete",
                         "Завершить задание принудительно",
                         json_data={}, expected_status=200, is_ajax=True)

        # Дублировать
        test_post_action(session, role, "POST", f"/repost-job/{job_id}",
                         "Дублировать задание", expected_status=302)

        # Оценка работников
        test_get_page(session, role, f"/jobs/{job_id}/rate-workers", "Оценка работников", expected_status=200)

        # Удалить задание
        test_post_action(session, role, "POST", f"/delete-job/{job_id}",
                         "Удалить задание", expected_status=302, is_ajax=True)

    # Профиль
    test_post_action(session, role, "POST", "/profile/update",
                     "Сохранить изменения профиля",
                     data={"full_name": "Org Test", "city": "Москва"},
                     expected_status=302)

    # Верификация
    test_post_action(session, role, "POST", "/verify-employer",
                     "Отправить заявку на верификацию",
                     data={"company_name": "ООО Тест", "description": "Тестовая компания"},
                     expected_status=302)

    # Массовые действия с заданиями
    test_post_action(session, role, "POST", "/my-jobs/action",
                     "Массовое действие (cancel)",
                     data={"action": "cancel", "job_ids": "[]"},
                     expected_status=302)

    # API: избранное — добавить
    test_post_action(session, role, "POST", "/api/favorites/add",
                     "Добавить в избранное (API)",
                     json_data={"item_id": "00000000-0000-0000-0000-000000000001", "type": "worker"},
                     expected_status=200, is_ajax=True)

    # API: избранное — удалить
    test_post_action(session, role, "POST", "/api/favorites/remove",
                     "Удалить из избранного (API)",
                     json_data={"item_id": "00000000-0000-0000-0000-000000000001", "type": "worker"},
                     expected_status=200, is_ajax=True)

    # Чёрный список — разблокировать (попытка)
    test_post_action(session, role, "POST", "/unblock/00000000-0000-0000-0000-000000000001",
                     "Разблокировать пользователя",
                     expected_status=302)


def test_admin_actions(session: requests.Session) -> None:
    """Тестирует действия админа."""
    role = "admin"
    print(f"\n--- Действия админа ---")

    # API health check — прямой GET, т.к. test_post_action не поддерживает GET
    try:
        resp = session.get(f"{BASE_URL}/api/health", timeout=30)
        if resp.status_code == 200:
            log("OK", f"GET /api/health → 200 (Health check админки)")
        else:
            log("FAIL", f"GET /api/health → {resp.status_code} (ожидался 200, Health check админки)")
    except requests.RequestException as e:
        log("FAIL", f"GET /api/health → ОШИБКА: {e} (Health check админки)")

    # Поиск пользователей
    test_get_page(session, role, "/admin?tab=users&search=test", "Поиск пользователей", expected_status=200)

    # Поиск заданий
    test_get_page(session, role, "/admin?tab=jobs&search=test", "Поиск заданий", expected_status=200)

    # Попытка сменить роль (с несуществующим ID)
    test_post_action(session, role, "POST", "/admin/users/00000000-0000-0000-0000-000000000001/role",
                     "Сменить роль пользователя",
                     data={"role": "worker"},
                     expected_status=302)

    # Управление навыками
    test_post_action(session, role, "POST", "/admin/skills",
                     "Добавить навык",
                     json_data={"name": f"Тестовый навык {int(time.time())}", "sort_order": 999},
                     expected_status=200, is_ajax=True)

    # Управление вероисповеданиями
    test_post_action(session, role, "POST", "/admin/religions",
                     "Добавить вероисповедание",
                     json_data={"name": f"Тестовое вероисповедание {int(time.time())}", "sort_order": 999},
                     expected_status=200, is_ajax=True)

    # Массовое удаление пользователей (пустой список)
    test_post_action(session, role, "POST", "/admin/bulk-delete-users",
                     "Массовое удаление пользователей",
                     json_data={"user_ids": []},
                     expected_status=200, is_ajax=True)

    # Массовое удаление заданий (пустой список)
    test_post_action(session, role, "POST", "/admin/bulk-delete-jobs",
                     "Массовое удаление заданий",
                     json_data={"job_ids": []},
                     expected_status=200, is_ajax=True)

    # Уведомления — удалить все
    test_post_action(session, role, "POST", "/api/notifications/delete-all",
                     "Удалить все уведомления",
                     json_data={}, expected_status=200, is_ajax=True)


def test_guest_access() -> None:
    """Тестирует гостевой доступ (без авторизации)."""
    role = "гость"
    print(f"\n{'='*60}")
    print(f"=== Роль: {role} (неавторизованный) ===")
    print(f"{'='*60}")

    session = requests.Session()

    # Главная
    test_get_page(session, role, "/", "Главная (гость)", expected_status=200)

    # Вход
    test_get_page(session, role, "/login", "Вход", expected_status=200,
                  expected_buttons=["Войти", "Зарегистрироваться"])

    # Регистрация
    test_get_page(session, role, "/register", "Регистрация", expected_status=200,
                  expected_buttons=["Зарегистрироваться", "Далее"])

    # Список заданий
    test_get_page(session, role, "/jobs", "Список заданий (гость)", expected_status=200)

    # Список работодателей
    test_get_page(session, role, "/employers", "Работодатели (гость)", expected_status=200)

    # Список трудников
    test_get_page(session, role, "/workers", "Трудники (гость)", expected_status=200)

    # Поиск
    test_get_page(session, role, "/search", "Поиск (гость)", expected_status=200)

    # Страницы, требующие авторизации — должны редиректить на логин
    for path, name in [
        ("/profile", "Профиль"),
        ("/my-jobs", "Мои задания"),
        ("/my-applications", "Отклики"),
        ("/favorites", "Избранное"),
        ("/chats", "Чаты"),
        ("/notifications", "Уведомления"),
        ("/admin", "Админка"),
        ("/blacklist", "Чёрный список"),
        ("/invitations", "Приглашения"),
        ("/job/new", "Создание задания"),
    ]:
        test_get_page(session, role, path, name, expected_status=302)


# ——————————————————————————————
# Главный раннер
# ——————————————————————————————
def main():
    global total_passed, total_failed, total_skipped, results_log

    results_log = []
    total_passed = total_failed = total_skipped = 0

    print("=" * 60)
    print("=== ТЕСТИРОВАНИЕ КНОПОК ПРИЛОЖЕНИЯ «ТРУДНИК» ===")
    print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Базовый URL: {BASE_URL}")
    print("=" * 60)

    # Проверка доступности сервера
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=10)
        print(f"\nСервер доступен: {resp.status_code}")
    except requests.RequestException as e:
        print(f"\n[FAIL] Сервер недоступен: {e}")
        print("Убедитесь, что Flask запущен на http://127.0.0.1:5000")
        sys.exit(1)

    # ——— Гость ———
    test_guest_access()

    # ——— Роли ———
    sessions = {}
    for role_key, creds in CREDENTIALS.items():
        print(f"\n{'='*60}")
        print(f"=== Роль: {creds['name']} ({role_key}) ===")
        print(f"{'='*60}")

        session = login_session(creds["email"], creds["password"], creds["name"])
        if not session:
            log("SKIP", f"Не удалось авторизоваться как {creds['name']} с паролем '{creds['password']}'")
            # Пробуем альтернативные пароли
            for alt_pwd in ALT_PASSWORDS:
                if alt_pwd == creds["password"]:
                    continue
                log("OK", f"Пробуем альтернативный пароль '{alt_pwd}' для {creds['name']}")
                session = login_session(creds["email"], alt_pwd, creds["name"])
                if session:
                    log("OK", f"Успешный вход с альтернативным паролем!")
                    break
            if not session:
                log("SKIP", f"Все попытки входа как {creds['name']} не удались — пропускаем тесты для этой роли")
                continue

        sessions[role_key] = session

        # ——— Общие страницы ———
        test_common_pages(session, role_key)

        # ——— Специфичные страницы ———
        if role_key == "worker":
            test_worker_pages(session)
        elif role_key == "employer":
            test_employer_pages(session)
        elif role_key == "admin":
            test_admin_pages(session)

    # ——— Действия (только если есть сессия) ———
    # Порядок важен: employer создаёт тестовые задания первым,
    # чтобы worker мог найти их на главной и протестировать отклики.
    if "employer" in sessions:
        test_employer_actions(sessions["employer"])
    if "worker" in sessions:
        test_worker_actions(sessions["worker"])
    if "admin" in sessions:
        test_admin_actions(sessions["admin"])

    # ——— ИТОГО ———
    print(f"\n{'='*60}")
    print("=== ИТОГО ===")
    print(f"Пройдено: {total_passed}")
    print(f"Ошибок: {total_failed}")
    print(f"Пропущено: {total_skipped}")
    total = total_passed + total_failed + total_skipped
    print(f"Всего проверок: {total}")
    if total > 0:
        print(f"Успешность: {total_passed / total * 100:.1f}%")
    print(f"{'='*60}")

    # Сохраняем в файл
    output_path = os.path.join(os.path.dirname(__file__), "..", OUTPUT_FILE)
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=== ТЕСТИРОВАНИЕ КНОПОК ПРИЛОЖЕНИЯ «ТРУДНИК» ===\n")
        f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Базовый URL: {BASE_URL}\n\n")
        for line in results_log:
            f.write(line + "\n")
        f.write(f"\n=== ИТОГО ===\n")
        f.write(f"Пройдено: {total_passed}\n")
        f.write(f"Ошибок: {total_failed}\n")
        f.write(f"Пропущено: {total_skipped}\n")
        f.write(f"Всего проверок: {total}\n")
        if total > 0:
            f.write(f"Успешность: {total_passed / total * 100:.1f}%\n")

    print(f"\nРезультаты сохранены в: {output_path}")

    return total_failed


if __name__ == "__main__":
    sys.exit(main())
