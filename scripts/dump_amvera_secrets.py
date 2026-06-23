#!/usr/bin/env python3
"""
Amvera Secrets Dumper — перехватывает API-ответы Amvera с переменными окружения.
Использует Playwright для входа в Amvera и перехвата network responses.

Запуск:
    python scripts/dump_amvera_secrets.py
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

sys.stdout.reconfigure(encoding='utf-8')

# Конфигурация
AMVERA_URL = "https://cloud.amvera.ru"
AMVERA_LOGIN = "Hyperstls"
AMVERA_PASSWORD = "Step@1986"
DEFAULT_TIMEOUT = 15000
NAVIGATION_TIMEOUT = 20000
SLOW_MO = 150

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "screenshots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Список переменных, которые ищем
TARGET_VARS = [
    'SECRET_KEY', 'DATABASE_URL', 'REDIS_URL', 'SMTP_PASSWORD',
    'VAPID_PRIVATE_KEY', 'VAPID_PUBLIC_KEY', 'YANDEX_MAPS_API_KEY',
    'PGRST_JWT_SECRET', 'POSTGREST_URL', 'SMTP_USER', 'SMTP_HOST',
    'SMTP_PORT', 'SMTP_FROM_EMAIL', 'SMTP_FROM_NAME',
    'VAPID_CLAIMS_EMAIL', 'WEBSOCKET_PORT', 'DEPLOYMENT_ENV',
    'WORKER_SITE_URL', 'GIT_VERSION', 'DEEPSEEK_API_KEY',
]

# Хранилище перехваченных ответов
captured_responses = []


async def on_response(response):
    """Перехватчик всех сетевых ответов."""
    try:
        url = response.url
        status = response.status
        content_type = response.headers.get('content-type', '')

        # Интересуют только JSON-ответы от API Amvera
        if 'application/json' in content_type and status == 200:
            try:
                body = await response.json()
                body_str = json.dumps(body, ensure_ascii=False)

                # Проверяем, содержит ли ответ какие-либо из целевых переменных
                found_vars = [v for v in TARGET_VARS if v in body_str]
                if found_vars:
                    captured_responses.append({
                        'url': url,
                        'status': status,
                        'found_vars': found_vars,
                        'body': body,
                    })
                    print(f"   [CAPTURED] {url} — найдены: {', '.join(found_vars)}")
            except Exception:
                pass  # Не JSON или не можем распарсить
    except Exception:
        pass


async def main():
    print("=" * 60)
    print("==> Amvera Secrets Dumper — перехват переменных окружения")
    print(f"   Время: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=SLOW_MO,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
        )
        page = await context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)

        # Регистрируем перехватчик ответов
        page.on("response", on_response)

        try:
            # ── Шаг 1: Вход в Amvera ──
            print("\n[1] Вход в Amvera...")
            await page.goto(f"{AMVERA_URL}/login", wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
            await asyncio.sleep(3)

            # Заполняем логин
            await page.wait_for_selector("#username", timeout=5000)
            await page.fill("#username", AMVERA_LOGIN)
            await page.fill("#password", AMVERA_PASSWORD)
            print("   [OK] Логин/пароль заполнены")

            # Нажимаем вход
            await page.click("#kc-login")
            print("   [OK] Кнопка входа нажата")

            # Ждём завершения OAuth-редиректа (Keycloak → Amvera)
            await asyncio.sleep(8)  # Даём время на OAuth callback
            current_url = page.url
            print(f"   [INFO] URL после входа: {current_url}")

            # Если всё ещё на /login — пробуем перейти напрямую
            if "/login" in current_url:
                print("   [WARN] Застряли на /login, пробуем перейти на /projects...")
                await page.goto(f"{AMVERA_URL}/projects", wait_until="domcontentloaded", timeout=30000)
            elif "id.amvera.ru" in current_url:
                print("   [WARN] Всё ещё на Keycloak, ждём ещё...")
                await asyncio.sleep(5)

            await asyncio.sleep(3)
            current_url = page.url
            print(f"   [INFO] Текущий URL: {current_url}")

            # ── Шаг 2: Переход к проекту ──
            print("\n[2] Переход к проекту trudnik...")
            if "/project" not in current_url:
                await page.goto(f"{AMVERA_URL}/projects", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

            # Ищем и кликаем по trudnik
            try:
                await page.click("text=trudnik", timeout=5000)
                print("   [OK] Проект trudnik открыт")
            except Exception:
                if "trudnik" in page.url.lower():
                    print("   [OK] Уже внутри проекта trudnik")
                else:
                    print("   [WARN] Не удалось найти проект trudnik, пробуем прямой URL")
                    # Пробуем прямой URL (возможный формат Amvera)
                    await page.goto(f"{AMVERA_URL}/project/trudnik", wait_until="domcontentloaded", timeout=15000)

            await asyncio.sleep(3)

            # ── Шаг 3: Переход к сервисам ──
            print("\n[3] Переход к сервисам...")
            services_clicked = False
            for sel in [
                'a:has-text("Сервисы")',
                'button:has-text("Сервисы")',
                'span:has-text("Сервисы")',
                'a:has-text("Services")',
            ]:
                try:
                    await page.click(sel, timeout=3000)
                    services_clicked = True
                    print(f"   [OK] Сервисы открыты через: {sel}")
                    break
                except Exception:
                    continue

            if not services_clicked:
                current = page.url.rstrip("/")
                await page.goto(f"{current}/services", wait_until="domcontentloaded", timeout=15000)
                print("   --> Перешли на /services")

            await asyncio.sleep(3)

            # ── Шаг 4: Открыть trudnik-app ──
            print("\n[4] Открытие trudnik-app...")
            for sel in [
                'a:has-text("trudnik-app")',
                'div:has-text("trudnik-app")',
                'span:has-text("trudnik-app")',
                'text=trudnik-app',
            ]:
                try:
                    await page.click(sel, timeout=5000)
                    print(f"   [OK] trudnik-app открыт через: {sel}")
                    break
                except Exception:
                    continue
            else:
                print("   [WARN] trudnik-app не найден")

            await asyncio.sleep(3)

            # ── Шаг 5: Открыть вкладку Переменные ──
            print("\n[5] Открытие вкладки 'Переменные'...")
            for sel in [
                'button:has-text("Переменные")',
                'a:has-text("Переменные")',
                'span:has-text("Переменные")',
                'button:has-text("Environment")',
                '.tab:has-text("Переменные")',
                'text=Переменные',
                'text=Environment',
            ]:
                try:
                    await page.click(sel, timeout=5000)
                    print(f"   [OK] Вкладка Переменные открыта через: {sel}")
                    break
                except Exception:
                    continue
            else:
                print("   [WARN] Вкладка Переменные не найдена")

            # Ждём загрузки данных (API-запросы)
            print("\n[6] Ожидание загрузки данных (10 секунд)...")
            await asyncio.sleep(10)

            # ── Сохраняем результаты ──
            print("\n" + "=" * 60)
            print(f"[РЕЗУЛЬТАТ] Перехвачено ответов с переменными: {len(captured_responses)}")

            if captured_responses:
                # Извлекаем все переменные из ответов
                all_env = {}
                for resp in captured_responses:
                    body = resp['body']
                    # Рекурсивно ищем переменные в JSON
                    _extract_env_vars(body, all_env)

                # Сохраняем в JSON
                output_file = OUTPUT_DIR / "amvera_secrets.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "captured_count": len(captured_responses),
                        "environment": all_env,
                        "raw_responses": captured_responses,
                    }, f, ensure_ascii=False, indent=2)
                print(f"[OK] Секреты сохранены в: {output_file}")

                # Выводим найденные переменные
                print("\n" + "=" * 60)
                print("НАЙДЕННЫЕ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ:")
                print("=" * 60)
                for key, value in sorted(all_env.items()):
                    masked = value[:3] + "***" if len(value) > 40 else value
                    print(f"   {key} = {masked}")
            else:
                print("[WARN] Ни один API-ответ не содержал целевых переменных.")
                print("   Сохраняю скриншот для отладки...")
                await page.screenshot(path=str(OUTPUT_DIR / "debug_no_vars_found.png"), full_page=True)
                print(f"   Скриншот: {OUTPUT_DIR / 'debug_no_vars_found.png'}")

        except Exception as e:
            print(f"\n[FAIL] КРИТИЧЕСКАЯ ОШИБКА: {e}")
            import traceback
            traceback.print_exc()
            try:
                await page.screenshot(path=str(OUTPUT_DIR / "critical_error.png"), full_page=True)
            except Exception:
                pass
        finally:
            await browser.close()

    print("\n[OK] Готово!")


def _extract_env_vars(obj, result: dict, prefix: str = ""):
    """Рекурсивно извлекает переменные окружения из JSON-объекта."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_prefix = f"{prefix}.{key}" if prefix else key

            # Если ключ совпадает с целевой переменной
            if key in TARGET_VARS and isinstance(value, str):
                result[key] = value
            # Если значение — словарь "env" с парами ключ-значение
            elif key in ("env", "environment", "variables", "secrets") and isinstance(value, dict):
                for env_key, env_val in value.items():
                    if isinstance(env_val, str):
                        result[env_key] = env_val
            # Если нашли массив переменных
            elif key in ("envVars", "env_vars", "environmentVariables") and isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and "name" in item and "value" in item:
                        result[item["name"]] = item.get("value", "")

            # Рекурсивно обходим
            _extract_env_vars(value, result, new_prefix)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _extract_env_vars(item, result, f"{prefix}[{i}]" if prefix else f"[{i}]")


if __name__ == "__main__":
    asyncio.run(main())
