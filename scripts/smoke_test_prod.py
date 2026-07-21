#!/usr/bin/env python3
"""
Smoke-тестирование production-окружения «Трудник».
Все тесты READ-ONLY — не создают/изменяют/удаляют данные.
"""

import sys
import re
import os
import requests

# ═══════════════════════════════════════════════════════════
# Конфигурация
# ═══════════════════════════════════════════════════════════
PROD_URL = os.environ.get("SMOKE_PROD_URL", "https://trudnik-hyperstls.amvera.io")
TEST_CREDENTIALS = {
    "worker": {
        "email": os.environ.get("SMOKE_WORKER_EMAIL", "org@test.ru"),
        "password": os.environ.get("SMOKE_WORKER_PASSWORD"),
    },
    "admin": {
        "email": os.environ.get("SMOKE_ADMIN_EMAIL", "admin@test.ru"),
        "password": os.environ.get("SMOKE_ADMIN_PASSWORD"),
    },
}
TIMEOUT = int(os.environ.get("SMOKE_TIMEOUT", "30"))

results = []
all_passed = True


def record(label, url, status_code, ok, detail=""):
    global all_passed
    status = "OK" if ok else "FAIL"
    if not ok:
        all_passed = False
    results.append((label, url, status_code, status, detail))
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon} [{status_code}] {label}: {url}{' -- ' + detail if detail else ''}")


if __name__ == '__main__':
    # ═══════════════════════════════════════════════════════════
    # Шаг 2: Проверить доступность основных страниц (GET, без авторизации)
    # ═══════════════════════════════════════════════════════════
    print("=" * 60)
    print("ШАГ 2: Проверка доступности публичных страниц (GET, без авторизации)")
    print("=" * 60)

    public_urls = [
        ("Главная", "/"),
        ("Страница входа", "/login"),
        ("Страница регистрации", "/register"),
        ("Список работодателей", "/employers"),
        ("Health-check", "/admin/health"),
    ]

    session = requests.Session()

    for label, path in public_urls:
        url = f"{PROD_URL}{path}"
        try:
            resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
            ok = resp.status_code == 200
            detail = ""
            if resp.status_code == 302:
                detail = f"редирект на {resp.headers.get('Location', '?')}"
            record(label, url, resp.status_code, ok, detail)
        except requests.RequestException as e:
            record(label, url, 0, False, str(e)[:100])

    # ═══════════════════════════════════════════════════════════
    # Шаг 3: Проверить доступность авторизованных страниц
    # ═══════════════════════════════════════════════════════════
    print()
    print("=" * 60)
    print("ШАГ 3: Проверка авторизованных страниц")
    print("=" * 60)


    def login(sess, email, password):
        """Выполнить вход и вернуть True в случае успеха."""
        login_url = f"{PROD_URL}/login"
        try:
            resp = sess.post(
                login_url,
                data={"email": email, "password": password},
                timeout=TIMEOUT,
                allow_redirects=False,
            )
            # Успешный вход даёт 302 редирект
            return resp.status_code in (302, 200)
        except requests.RequestException:
            return False


    # --- Вход как обычный пользователь (org@test.ru) ---
    print("\n  Логин как org@test.ru ...")
    if not TEST_CREDENTIALS["worker"]["password"]:
        print("  [SKIP] SMOKE_WORKER_PASSWORD не задан, вход пропущен")
        record("Вход org@test.ru (пропущен)", f"{PROD_URL}/login", "SKIP", True, "пароль не задан")
    elif login(session, TEST_CREDENTIALS["worker"]["email"], TEST_CREDENTIALS["worker"]["password"]):
        print("  [OK] Вход выполнен")

        # Проверяем страницы, доступные обычному пользователю
        user_authed_urls = [
            ("Мои вакансии (my-jobs)", "/my-jobs"),
            ("Профиль (profile)", "/profile"),
        ]
        for label, path in user_authed_urls:
            url = f"{PROD_URL}{path}"
            try:
                resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
                # Если редиректит на login — значит не пускает
                if resp.status_code == 200 and "login" not in resp.url.lower():
                    record(label, url, resp.status_code, True)
                elif resp.status_code == 200:
                    record(label, url, resp.status_code, False, "вернулась страница логина (нет доступа)")
                else:
                    record(label, url, resp.status_code, resp.status_code == 200)
            except requests.RequestException as e:
                record(label, url, 0, False, str(e)[:100])
    else:
        print("  [FAIL] Не удалось войти как org@test.ru")
        record("Вход org@test.ru", f"{PROD_URL}/login", 0, False, "не удалось залогиниться")

    # --- Вход как админ (admin@test.ru) — новая сессия ---
    print("\n  Логин как admin@test.ru ...")
    admin_session = requests.Session()
    if not TEST_CREDENTIALS["admin"]["password"]:
        print("  [SKIP] SMOKE_ADMIN_PASSWORD не задан, вход пропущен")
        record("Вход admin@test.ru (пропущен)", f"{PROD_URL}/login", "SKIP", True, "пароль не задан")
    elif login(admin_session, TEST_CREDENTIALS["admin"]["email"], TEST_CREDENTIALS["admin"]["password"]):
        print("  [OK] Вход админа выполнен")

        # Проверяем админку
        admin_url = f"{PROD_URL}/admin"
        try:
            resp = admin_session.get(admin_url, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code == 200 and "login" not in resp.url.lower():
                record("Админ-панель (admin)", admin_url, resp.status_code, True)
            elif resp.status_code == 200:
                record("Админ-панель (admin)", admin_url, resp.status_code, False, "вернулась страница логина (нет доступа)")
            else:
                record("Админ-панель (admin)", admin_url, resp.status_code, resp.status_code == 200)
        except requests.RequestException as e:
            record("Админ-панель (admin)", admin_url, 0, False, str(e)[:100])
    else:
        print("  [FAIL] Не удалось войти как admin@test.ru")
        record("Вход admin@test.ru", f"{PROD_URL}/login", 0, False, "не удалось залогиниться")

    # ═══════════════════════════════════════════════════════════
    # Шаг 4: Проверить API-эндпоинты
    # ═══════════════════════════════════════════════════════════
    print()
    print("=" * 60)
    print("ШАГ 4: Проверка API-эндпоинтов (админская сессия)")
    print("=" * 60)

    api_url = f"{PROD_URL}/api/admin/job-stats"
    try:
        resp = admin_session.get(api_url, timeout=TIMEOUT)
        is_json = "application/json" in resp.headers.get("Content-Type", "")
        if resp.status_code == 200 and is_json:
            try:
                data = resp.json()
                record("API job-stats", api_url, resp.status_code, True, f"JSON получен, ключей: {len(data) if isinstance(data, dict) else '?'}")
            except Exception:
                record("API job-stats", api_url, resp.status_code, False, "ответ не является валидным JSON")
        elif resp.status_code == 200:
            record("API job-stats", api_url, resp.status_code, False, f"Content-Type: {resp.headers.get('Content-Type', '?')}, body: {resp.text[:100]}")
        else:
            record("API job-stats", api_url, resp.status_code, False, f"HTTP {resp.status_code}")
    except requests.RequestException as e:
        record("API job-stats", api_url, 0, False, str(e)[:100])

    # ═══════════════════════════════════════════════════════════
    # Шаг 5: Проверить фильтрацию и поиск
    # ═══════════════════════════════════════════════════════════
    print()
    print("=" * 60)
    print("ШАГ 5: Проверка фильтрации и поиска")
    print("=" * 60)

    filter_urls = [
        ("Фильтр: skills=Уборка", "/?skills=Уборка"),
        ("Сортировка: sort=newest", "/?sort=newest"),
    ]

    for label, path in filter_urls:
        url = f"{PROD_URL}{path}"
        try:
            resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
            record(label, url, resp.status_code, resp.status_code == 200)
        except requests.RequestException as e:
            record(label, url, 0, False, str(e)[:100])

    # ═══════════════════════════════════════════════════════════
    # Шаг 6: Итоговая сводка
    # ═══════════════════════════════════════════════════════════
    print()
    print("=" * 60)
    print("ИТОГОВАЯ СВОДКА")
    print("=" * 60)

    print(f"\n{'№':<4} {'Статус':<6} {'Код':<6} {'Тест':<35} {'URL'}")
    print("-" * 100)
    for i, (label, url, status_code, status, detail) in enumerate(results, 1):
        print(f"{i:<4} {status:<6} {status_code:<6} {label:<35} {url}")
        if detail:
            print(f"     {'':>6} {'':>6} -> {detail}")

    print("-" * 100)
    passed = sum(1 for _, _, _, s, _ in results if s == "OK")
    failed = sum(1 for _, _, _, s, _ in results if s == "FAIL")
    total = len(results)
    print(f"\n  Всего тестов: {total}")
    print(f"  Пройдено:     {passed}")
    print(f"  Провалено:    {failed}")

    if all_passed:
        print("\n  [OK] SMOKE-ТЕСТИРОВАНИЕ ПРОЙДЕНО УСПЕШНО!")
        sys.exit(0)
    else:
        print(f"\n  [FAIL] SMOKE-ТЕСТИРОВАНИЕ НЕ ПРОЙДЕНО ({failed} FAIL)")
        sys.exit(1)
