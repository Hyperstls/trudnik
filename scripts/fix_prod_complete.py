#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fix_prod_complete.py — полная диагностика и настройка prod на Amvera.

Скрипт проверяет доступность приложения, логинится как admin,
собирает CSRF-токен, проверяет API-эндпоинты и даёт инструкции
по исправлению проблем с PostgREST.

Использование:
    python scripts/fix_prod_complete.py
"""

import io
import re
import sys
import json
from urllib.parse import urljoin

import requests

# ── Настройка вывода UTF-8 ────────────────────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ── Конфигурация ──────────────────────────────────────────
BASE_URL = "https://trudnik-hyperstls.amvera.io"
ADMIN_EMAIL = "admin@test.ru"
ADMIN_PASSWORD = "Step@1986"

# Сессия с сохранением cookies между запросами
session = requests.Session()
session.headers.update({
    "User-Agent": "fix-prod-complete/1.0 (diagnostic script)",
})


def main():
    print("=" * 65)
    print("  fix_prod_complete.py — Диагностика prod на Amvera")
    print("=" * 65)

    # ── 1. Проверить доступность приложения ────────────────
    print("\n── 1. Проверка доступности ──")

    # /health — глубокий health-check с проверкой PostgREST
    try:
        r = session.get(urljoin(BASE_URL, "/health"), timeout=30)
        print(f"   GET /health → HTTP {r.status_code}")
        if r.ok:
            data = r.json()
            print(f"   Ответ: {json.dumps(data, ensure_ascii=False)}")
        else:
            print(f"   Тело: {r.text[:300]}")
    except requests.ConnectionError as e:
        print(f"   ❌ ОШИБКА СОЕДИНЕНИЯ: {e}")
        print(f"   Сайт {BASE_URL} недоступен. Проверь, запущен ли trudnik-app в Amvera.")
        return 1
    except Exception as e:
        print(f"   ❌ ОШИБКА: {e}")

    # /api/health — лёгкий health-check (без PostgREST)
    try:
        r = session.get(urljoin(BASE_URL, "/api/health"), timeout=15)
        print(f"   GET /api/health → HTTP {r.status_code}")
        if r.ok:
            print(f"   Ответ: {json.dumps(r.json(), ensure_ascii=False)}")
    except Exception as e:
        print(f"   ⚠ /api/health недоступен: {e}")

    # ── 2. Залогиниться как admin ──────────────────────────
    print("\n── 2. Логин как admin ──")

    login_ok = False
    try:
        r = session.post(
            urljoin(BASE_URL, "/login"),
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            allow_redirects=False,  # не ходить по редиректу, анализируем ответ
            timeout=30,
        )
        print(f"   POST /login → HTTP {r.status_code}")

        # Успешный логин → 302 редирект на /jobs или /jobs/my_jobs
        if r.status_code in (302, 303) and r.headers.get("Location"):
            print(f"   Редирект → {r.headers['Location']}")
            login_ok = True

            # Пройти по редиректу, чтобы сессия закрепилась
            redirect_url = urljoin(BASE_URL, r.headers["Location"])
            r2 = session.get(redirect_url, timeout=30)
            print(f"   GET {r.headers['Location']} → HTTP {r2.status_code}")

            if r2.status_code == 200:
                login_ok = True
            else:
                print(f"   ⚠ Редирект вернул {r2.status_code} (не 200)")
                # Попробуем явно перейти на главную
                r3 = session.get(urljoin(BASE_URL, "/"), timeout=30)
                print(f"   GET / → HTTP {r3.status_code}")

        elif r.status_code == 200:
            # Возможно, вернулась страница логина с flash-сообщением об ошибке
            if "неверный email или пароль" in r.text.lower():
                print("   ❌ Неверный email или пароль")
            elif "ошибка" in r.text.lower():
                # Попробуем найти flash-сообщение
                flash_match = re.search(
                    r'class="[^"]*alert[^"]*"[^>]*>(.*?)</div>',
                    r.text,
                    re.DOTALL | re.IGNORECASE,
                )
                if flash_match:
                    flash_text = re.sub(r"<[^>]+>", "", flash_match.group(1)).strip()
                    print(f"   Flash: {flash_text}")
                else:
                    print("   ⚠ Логин не удался (HTTP 200 без редиректа)")
            else:
                print("   ⚠ Логин не удался (HTTP 200 без редиректа)")
        else:
            print(f"   ⚠ Неожиданный статус: {r.status_code}")
            print(f"   Тело: {r.text[:500]}")

    except Exception as e:
        print(f"   ❌ ОШИБКА при логине: {e}")

    # ── 3. Получить CSRF-токен с админ-панели ─────────────
    print("\n── 3. CSRF-токен ──")

    csrf_token = None
    try:
        r = session.get(urljoin(BASE_URL, "/admin"), timeout=30)
        print(f"   GET /admin → HTTP {r.status_code}")

        if r.status_code == 200:
            # Ищем CSRF-токен в HTML (мета-тег, скрытый input, data-атрибут)
            patterns = [
                r'<meta\s+name="csrf-token"\s+content="([^"]+)"',
                r'<meta\s+name="csrf_token"\s+content="([^"]+)"',
                r'<input\s+type="hidden"\s+name="_csrf_token"\s+value="([^"]+)"',
                r'data-csrf-token="([^"]+)"',
                r'csrf_token\s*[:=]\s*["\']([^"\']+)["\']',
            ]
            for pattern in patterns:
                match = re.search(pattern, r.text, re.IGNORECASE)
                if match:
                    csrf_token = match.group(1)
                    print(f"   ✅ CSRF-токен найден: {csrf_token[:16]}...")
                    break

            if not csrf_token:
                # Попробовать найти в JavaScript-переменных
                js_match = re.search(
                    r'(?:csrf[_-]?token|_csrf)\s*[:=]\s*["\']([^"\']+)["\']',
                    r.text,
                    re.IGNORECASE,
                )
                if js_match:
                    csrf_token = js_match.group(1)
                    print(f"   ✅ CSRF-токен из JS: {csrf_token[:16]}...")

            if not csrf_token:
                print("   ⚠ CSRF-токен не найден в HTML (возможно, в cookie сессии)")
                # Проверим cookies сессии
                for cookie in session.cookies:
                    if "csrf" in cookie.name.lower():
                        print(f"   Cookie: {cookie.name} = {cookie.value[:32]}...")
        elif r.status_code == 302:
            print(f"   Редирект на {r.headers.get('Location', '?')} → недостаточно прав (не admin)")
            # Возможно, пользователь не admin — проверим
            r2 = session.get(urljoin(BASE_URL, "/"), timeout=15)
            if "выход" in r2.text.lower() or "logout" in r2.text.lower():
                print("   Похоже, пользователь залогинен, но не имеет роли admin")
    except Exception as e:
        print(f"   ❌ ОШИБКА при получении CSRF: {e}")

    # ── 4. Проверить данные API ────────────────────────────
    print("\n── 4. Проверка API-данных ──")

    religions_count = 0
    skills_count = 0

    # /api/religions
    try:
        r = session.get(urljoin(BASE_URL, "/api/religions"), timeout=30)
        print(f"   GET /api/religions → HTTP {r.status_code}")
        if r.ok:
            data = r.json()
            religions = data.get("religions", [])
            religions_count = len(religions)
            print(f"   Религий в справочнике: {religions_count}")
            if religions:
                for rel in religions[:5]:
                    print(f"     - {rel.get('name', '?')}")
                if len(religions) > 5:
                    print(f"     ... и ещё {len(religions) - 5}")
        else:
            print(f"   Тело: {r.text[:200]}")
    except Exception as e:
        print(f"   ❌ ОШИБКА /api/religions: {e}")

    # /api/skills
    try:
        r = session.get(urljoin(BASE_URL, "/api/skills"), timeout=30)
        print(f"   GET /api/skills → HTTP {r.status_code}")
        if r.ok:
            data = r.json()
            skills = data.get("skills", [])
            skills_count = len(skills)
            print(f"   Навыков в справочнике: {skills_count}")
            if skills:
                for sk in skills[:5]:
                    print(f"     - {sk.get('name', '?')}")
                if len(skills) > 5:
                    print(f"     ... и ещё {len(skills) - 5}")
        else:
            print(f"   Тело: {r.text[:200]}")
    except Exception as e:
        print(f"   ❌ ОШИБКА /api/skills: {e}")

    # ── 5. Резюме ──────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  РЕЗЮМЕ ДИАГНОСТИКИ")
    print("=" * 65)
    print(f"   Логин admin:       {'✅ ОК' if login_ok else '❌ ПРОВАЛ'}")
    print(f"   CSRF-токен:        {'✅ Найден' if csrf_token else '⚠ Не найден'}")
    print(f"   Религий в API:     {religions_count}")
    print(f"   Навыков в API:     {skills_count}")
    print(f"   Данные в API:      {'✅ Есть' if (religions_count > 0 and skills_count > 0) else '❌ ПУСТО'}")

    # ── 6. Инструкция ──────────────────────────────────────
    if religions_count == 0 or skills_count == 0:
        print("\n" + "!" * 65)
        print("  ПРОБЛЕМА: Flask не может подключиться к PostgREST")
        print("!" * 65)
        print("""
   Проверь в Amvera Cloud (https://cloud.amvera.ru):

   1. trudnik-app → Переменные → POSTGREST_URL
       Должно быть: http://amvera-hyperstls-run-trudnik-pr
       (или имя твоего postgrest-сервиса, порт назначается Amvera через $PORT)

   2. trudnik-pr → Статус
      Должно быть: «Запущено» (зелёный индикатор)

   3. После изменения POSTGREST_URL:
      Перезапусти trudnik-app (кнопка «Перезапустить»)

   4. Также проверь переменную PGRST_JWT_SECRET:
      Должна совпадать с JWT-секретом в trudnik-pr

   5. Если всё верно, но данные всё равно пустые:
      Зайди в trudnik-pr → Логи → проверь, нет ли ошибок
      при старте или обработке запросов.
""")
        return 2

    print("\n   ✅ Все проверки пройдены. Данные доступны.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
