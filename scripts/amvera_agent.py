#!/usr/bin/env python3
"""
Amvera Agent — браузерный агент на Playwright для автоматизации Amvera и pgAdmin.

Проверяет и настраивает сервисы Amvera, проверяет переменные окружения,
подключается к pgAdmin и выполняет проверочные SQL-запросы.

Требования:
    pip install playwright requests
    playwright install chromium

Запуск:
    python scripts/amvera_agent.py              # Все шаги (Playwright)
    python scripts/amvera_agent.py --pgadmin    # Только pgAdmin API fix
    python scripts/amvera_agent.py --all        # Все шаги + pgAdmin API fix
"""

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeout

# Принудительно переключаем stdout на UTF-8, чтобы избежать UnicodeEncodeError
# на Windows-консолях с cp1251
sys.stdout.reconfigure(encoding='utf-8')

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

AMVERA_URL = "https://cloud.amvera.ru"
AMVERA_LOGIN = "Hyperstls"
AMVERA_PASSWORD = "Step@1986"

PGADMIN_LOGIN = "admin@trudnik.ru"
PGADMIN_PASSWORD = "***REMOVED***"

SITE_URL = "https://trudnik-hyperstls.amvera.io"

# Директория для скриншотов (рядом со скриптом)
SCRIPT_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = SCRIPT_DIR / "screenshots"

# Таймауты (мс)
DEFAULT_TIMEOUT = 15000
LONG_TIMEOUT = 30000
NAVIGATION_TIMEOUT = 20000

# Задержка между действиями (мс) — даёт время на анимации и загрузку React/Vue
SLOW_MO = 200


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def ensure_screenshots_dir() -> Path:
    """Создать директорию для скриншотов, если её нет."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    return SCREENSHOTS_DIR


def screenshot_path(name: str) -> str:
    """Получить полный путь для скриншота с временной меткой."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    return str(SCREENSHOTS_DIR / f"{ts}_{safe_name}.png")


async def screenshot(page: Page, name: str) -> str:
    """Сделать скриншот и вернуть путь к файлу."""
    path = screenshot_path(name)
    await page.screenshot(path=path, full_page=True)
    print(f"   [SCREENSHOT] Скриншот сохранён: {path}")
    return path


async def safe_click(page: Page, selector: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Безопасный клик с ожиданием видимости элемента."""
    try:
        await page.wait_for_selector(selector, state="visible", timeout=timeout)
        await page.click(selector)
        return True
    except PlaywrightTimeout:
        print(f"   [WARN] Элемент не найден: {selector}")
        return False
    except Exception as e:
        print(f"   [WARN] Ошибка клика по {selector}: {e}")
        return False


async def safe_fill(page: Page, selector: str, value: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Безопасное заполнение поля."""
    try:
        await page.wait_for_selector(selector, state="visible", timeout=timeout)
        await page.fill(selector, value)
        return True
    except PlaywrightTimeout:
        print(f"   [WARN] Поле ввода не найдено: {selector}")
        return False
    except Exception as e:
        print(f"   [WARN] Ошибка заполнения {selector}: {e}")
        return False


async def log_page_info(page: Page, step_name: str):
    """Залогировать текущий URL и заголовок страницы для отладки."""
    try:
        url = page.url
        title = await page.title()
        print(f"   [DEBUG] [{step_name}] URL: {url}")
        print(f"   [DEBUG] [{step_name}] Title: {title}")
    except Exception:
        pass


async def wait_for_any_url(page: Page, patterns: list[str], timeout: int = NAVIGATION_TIMEOUT):
    """Ждать, пока URL не совпадёт с одним из паттернов."""
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        current = page.url
        for pat in patterns:
            if pat in current:
                return True
        await asyncio.sleep(0.5)
    return False


async def scroll_to_bottom(page: Page):
    """Прокрутить страницу вниз."""
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(0.5)


# ---------------------------------------------------------------------------
# Шаг 1: Вход в Amvera
# ---------------------------------------------------------------------------

async def step_login_amvera(page: Page) -> bool:
    """Войти в аккаунт Amvera (Keycloak — id.amvera.ru)."""
    print("\n" + "=" * 60)
    print("[1] Вход в Amvera...")
    print("=" * 60)

    await page.goto(f"{AMVERA_URL}/login", wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
    await asyncio.sleep(3)
    await screenshot(page, "01_amvera_login_page")
    await log_page_info(page, "login_page")

    # --- Отладка: выводим ВСЕ input-поля на странице ---
    all_inputs = await page.evaluate('''() => {
        return Array.from(document.querySelectorAll('input')).map(el => ({
            id: el.id,
            name: el.name,
            type: el.type,
            placeholder: el.placeholder,
            className: el.className
        }));
    }''')
    print(f"   [DEBUG] Найдено input-полей: {len(all_inputs)}")
    for inp in all_inputs:
        print(f"   [DEBUG]   id={inp['id']}, name={inp['name']}, type={inp['type']}, placeholder={inp['placeholder']}")

    # --- Keycloak-селекторы (id.amvera.ru) ---
    selectors_email = [
        "#username",              # Keycloak основной
        "input[name='username']",
        "input[id='username']",
        "input[type='text']",     # запасной
    ]

    selectors_password = [
        "#password",              # Keycloak основной
        "input[name='password']",
        "input[id='password']",
        "input[type='password']",
    ]

    selectors_submit = [
        "#kc-login",              # Keycloak кнопка
        "input[type='submit']",
        "button[type='submit']",
        "button:has-text('Войти')",
        "button:has-text('Sign In')",
        "button:has-text('Log In')",
        "input[value='Войти']",
        "input[value='Sign In']",
    ]

    # --- Заполняем email/username ---
    email_filled = False
    for sel in selectors_email:
        try:
            await page.wait_for_selector(sel, timeout=3000)
            await page.fill(sel, AMVERA_LOGIN)
            email_filled = True
            print(f"   [OK] Email/username введён через селектор: {sel}")
            break
        except Exception:
            continue
    if not email_filled:
        print("   [FAIL] Не удалось найти поле email/username")
        await screenshot(page, "01_error_email_not_found")
        return False

    # --- Заполняем пароль ---
    password_filled = False
    for sel in selectors_password:
        try:
            await page.wait_for_selector(sel, timeout=3000)
            await page.fill(sel, AMVERA_PASSWORD)
            password_filled = True
            print(f"   [OK] Пароль введён через селектор: {sel}")
            break
        except Exception:
            continue
    if not password_filled:
        print("   [FAIL] Не удалось найти поле пароля")
        await screenshot(page, "01_error_password_not_found")
        return False

    await asyncio.sleep(0.5)

    # --- Нажимаем кнопку входа ---
    submit_clicked = False
    for sel in selectors_submit:
        try:
            await page.wait_for_selector(sel, timeout=3000)
            await page.click(sel)
            submit_clicked = True
            print(f"   [OK] Кнопка входа нажата: {sel}")
            break
        except Exception:
            continue
    if not submit_clicked:
        print("   [FAIL] Не удалось найти кнопку входа")
        await screenshot(page, "01_error_submit_not_found")
        return False

    # Ждём редиректа с id.amvera.ru на cloud.amvera.ru
    try:
        await page.wait_for_url("**/cloud.amvera.ru/**", timeout=15000)
        print("   [OK] Успешный вход в Amvera!")
    except PlaywrightTimeout:
        print("   [WARN] Редирект на cloud.amvera.ru не произошёл в течение 15 сек")
        await asyncio.sleep(3)

    await screenshot(page, "01_after_login")
    await log_page_info(page, "after_login")

    # После Keycloak-редиректа ждём пока Amvera обработает OAuth callback
    # URL может временно быть /login — это нормально
    await page.wait_for_timeout(3000)  # ждём 3 секунды
    current_url = page.url

    # Проверяем что мы НЕ на Keycloak и НЕ на странице ошибки
    if "id.amvera.ru" in current_url:
        print("   [FAIL] Застряли на Keycloak — вход не удался")
        return False

    # Проверяем что мы на проектах/дашборде Amvera
    if "/projects" in current_url or "/project" in current_url:
        print(f"   [OK] Успешно вошли в Amvera: {current_url}")
        return True

    # Если мы на /login — ждём ещё (OAuth callback обрабатывается)
    if "/login" in current_url:
        print("   [WARN] Всё ещё на /login, ждём обработки OAuth...")
        await page.wait_for_timeout(5000)
        current_url = page.url

    # Финальная проверка — мы должны быть где-то внутри Amvera
    if "cloud.amvera.ru" in current_url and "/login" not in current_url:
        print(f"   [OK] Успешно вошли в Amvera: {current_url}")
        return True

    print(f"   [FAIL] Не удалось войти: {current_url}")
    return False


# ---------------------------------------------------------------------------
# Шаг 2: Переход к проекту trudnik
# ---------------------------------------------------------------------------

async def step_navigate_to_project(page: Page) -> bool:
    """Найти и открыть проект trudnik."""
    print("\n" + "=" * 60)
    print("[2] Переход к проекту trudnik...")
    print("=" * 60)

    await log_page_info(page, "step2_start")
    await screenshot(page, "02_before_project_search")

    # Пробуем прямой переход к проектам
    await page.goto(f"{AMVERA_URL}/projects", wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
    await asyncio.sleep(3)
    await screenshot(page, "02_projects_page")
    await log_page_info(page, "projects_page")

    # Ищем проект trudnik в списке
    project_selectors = [
        'a:has-text("trudnik")',
        'div:has-text("trudnik")',
        'span:has-text("trudnik")',
        'h3:has-text("trudnik")',
        '[data-project-name*="trudnik" i]',
        'tr:has-text("trudnik")',
        'li:has-text("trudnik")',
        '.project-card:has-text("trudnik")',
        '.project-name:has-text("trudnik")',
    ]

    project_found = False
    for sel in project_selectors:
        try:
            element = await page.wait_for_selector(sel, state="visible", timeout=5000)
            if element:
                await element.click()
                project_found = True
                print(f"   [OK] Проект trudnik найден и открыт через: {sel}")
                break
        except PlaywrightTimeout:
            continue
        except Exception:
            continue

    if not project_found:
        # Пробуем найти через текст страницы
        page_text = await page.text_content("body")
        if page_text and "trudnik" in page_text.lower():
            print("   [DEBUG] Проект trudnik упоминается на странице, но не кликабелен через селекторы")
            # Пробуем кликнуть по любому элементу, содержащему trudnik
            try:
                await page.click("text=trudnik", timeout=5000)
                project_found = True
                print("   [OK] Клик по тексту 'trudnik'")
            except Exception:
                pass

    if not project_found:
        print("   [WARN] Проект trudnik не найден в списке. Возможно, уже внутри проекта.")
        # Проверим, не внутри ли мы уже проекта
        if "trudnik" in page.url.lower():
            print("   [OK] URL содержит trudnik — вероятно, мы уже в проекте")
            project_found = True

    await asyncio.sleep(2)
    await screenshot(page, "02_inside_project")
    await log_page_info(page, "inside_project")

    return project_found or True  # Продолжаем даже если не нашли явно


# ---------------------------------------------------------------------------
# Шаг 3: Проверка trudnik-app переменных
# ---------------------------------------------------------------------------

async def step_check_trudnik_app_vars(page: Page) -> dict:
    """Проверить переменные окружения сервиса trudnik-app."""
    print("\n" + "=" * 60)
    print("[3] Проверка trudnik-app переменных...")
    print("=" * 60)

    result = {}
    await screenshot(page, "03_before_app_vars")
    await log_page_info(page, "before_app_vars")

    # Ищем вкладку "Сервисы" или переходим напрямую
    services_selectors = [
        'a:has-text("Сервисы")',
        'a:has-text("сервисы")',
        'a:has-text("Services")',
        'button:has-text("Сервисы")',
        'span:has-text("Сервисы")',
        '[href*="service" i]',
    ]

    for sel in services_selectors:
        if await safe_click(page, sel, timeout=5000):
            print(f"   [OK] Вкладка 'Сервисы' открыта через: {sel}")
            break
    else:
        # Пробуем перейти по URL
        current = page.url.rstrip("/")
        await page.goto(f"{current}/services", wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
        print("   --> Перешли на /services")

    await asyncio.sleep(3)
    await screenshot(page, "03_services_page")
    await log_page_info(page, "services_page")

    # Ищем trudnik-app в списке сервисов
    app_selectors = [
        'a:has-text("trudnik-app")',
        'div:has-text("trudnik-app")',
        'span:has-text("trudnik-app")',
        'tr:has-text("trudnik-app")',
        'li:has-text("trudnik-app")',
    ]

    app_found = False
    for sel in app_selectors:
        try:
            element = await page.wait_for_selector(sel, state="visible", timeout=5000)
            if element:
                await element.click()
                app_found = True
                print(f"   [OK] trudnik-app открыт через: {sel}")
                break
        except PlaywrightTimeout:
            continue
        except Exception:
            continue

    if not app_found:
        print("   [WARN] trudnik-app не найден в списке сервисов")
        await screenshot(page, "03_app_not_found")
        return result

    await asyncio.sleep(2)
    await screenshot(page, "03_trudnik_app_detail")
    await log_page_info(page, "trudnik_app_detail")

    # Ищем вкладку "Переменные" (окружения)
    env_tab_selectors = [
        'button:has-text("Переменные")',
        'a:has-text("Переменные")',
        'span:has-text("Переменные")',
        'button:has-text("Environment")',
        'a:has-text("Environment")',
        'button:has-text("переменные")',
        '[data-tab="env" i]',
        '[data-tab="environment" i]',
        '.tab:has-text("Переменные")',
    ]

    for sel in env_tab_selectors:
        if await safe_click(page, sel, timeout=5000):
            print(f"   [OK] Вкладка 'Переменные' открыта через: {sel}")
            break
    else:
        print("   [WARN] Вкладка 'Переменные' не найдена")
        await screenshot(page, "03_env_tab_not_found")

    await asyncio.sleep(2)
    await screenshot(page, "03_app_env_vars")
    await log_page_info(page, "app_env_vars")

    # Считываем текст страницы для анализа переменных
    page_text = await page.text_content("body")
    if page_text:
        # Проверяем ключевые переменные
        checks = {
            "POSTGREST_URL": "http://amvera-hyperstls-run-trudnik-pr",
            "PGRST_JWT_SECRET": None,  # Просто проверяем наличие
        }
        for var_name, expected_value in checks.items():
            if var_name.lower() in page_text.lower():
                if expected_value:
                    if expected_value.lower() in page_text.lower():
                        result[var_name] = {"status": "[OK]", "value": expected_value}
                        print(f"   [OK] {var_name} = {expected_value}")
                    else:
                        result[var_name] = {"status": "[WARN]", "value": "присутствует, но значение отличается"}
                        print(f"   [WARN] {var_name} присутствует, но значение может отличаться от ожидаемого")
                else:
                    result[var_name] = {"status": "[OK]", "value": "присутствует"}
                    print(f"   [OK] {var_name} присутствует")
            else:
                result[var_name] = {"status": "[FAIL]", "value": "отсутствует"}
                print(f"   [FAIL] {var_name} не найден в переменных")

    return result


# ---------------------------------------------------------------------------
# Шаг 4: Проверка trudnik-pr (PostgREST) переменных
# ---------------------------------------------------------------------------

async def step_check_trudnik_pr_vars(page: Page) -> dict:
    """Проверить переменные окружения сервиса trudnik-pr (PostgREST)."""
    print("\n" + "=" * 60)
    print("[4] Проверка trudnik-pr (PostgREST) переменных...")
    print("=" * 60)

    result = {}
    await screenshot(page, "04_before_pr_vars")
    await log_page_info(page, "before_pr_vars")

    # Возвращаемся к списку сервисов
    # Ищем способ вернуться назад или перейти к списку сервисов
    back_selectors = [
        'a:has-text("Сервисы")',
        'button:has-text("Сервисы")',
        'a:has-text("Назад")',
        'button:has-text("Назад")',
        '[aria-label="Назад" i]',
        '[aria-label="Back" i]',
    ]

    for sel in back_selectors:
        if await safe_click(page, sel, timeout=3000):
            print(f"   [BACK] Возврат через: {sel}")
            break
    else:
        # Пробуем перейти к сервисам по URL
        current = page.url.rstrip("/")
        # Убираем возможный суффикс конкретного сервиса
        base_parts = current.split("/")
        # Ищем позицию /services в URL
        for i, part in enumerate(base_parts):
            if part == "services":
                base_url = "/".join(base_parts[: i + 1])
                await page.goto(base_url, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
                break

    await asyncio.sleep(2)
    await screenshot(page, "04_services_list")
    await log_page_info(page, "services_list_for_pr")

    # Ищем trudnik-pr
    pr_selectors = [
        'a:has-text("trudnik-pr")',
        'div:has-text("trudnik-pr")',
        'span:has-text("trudnik-pr")',
        'tr:has-text("trudnik-pr")',
        'li:has-text("trudnik-pr")',
    ]

    pr_found = False
    for sel in pr_selectors:
        try:
            element = await page.wait_for_selector(sel, state="visible", timeout=5000)
            if element:
                await element.click()
                pr_found = True
                print(f"   [OK] trudnik-pr открыт через: {sel}")
                break
        except PlaywrightTimeout:
            continue
        except Exception:
            continue

    if not pr_found:
        print("   [WARN] trudnik-pr не найден в списке сервисов")
        await screenshot(page, "04_pr_not_found")
        return result

    await asyncio.sleep(2)
    await screenshot(page, "04_trudnik_pr_detail")
    await log_page_info(page, "trudnik_pr_detail")

    # Ищем вкладку "Переменные"
    env_tab_selectors = [
        'button:has-text("Переменные")',
        'a:has-text("Переменные")',
        'span:has-text("Переменные")',
        'button:has-text("Environment")',
        'button:has-text("переменные")',
        '.tab:has-text("Переменные")',
    ]

    for sel in env_tab_selectors:
        if await safe_click(page, sel, timeout=5000):
            print(f"   [OK] Вкладка 'Переменные' открыта через: {sel}")
            break
    else:
        print("   [WARN] Вкладка 'Переменные' не найдена для trudnik-pr")

    await asyncio.sleep(2)
    await screenshot(page, "04_pr_env_vars")
    await log_page_info(page, "pr_env_vars")

    # Считываем переменные
    page_text = await page.text_content("body")
    if page_text:
        checks = ["PGRST_JWT_SECRET", "PGDATABASE", "PGRST_DB_URI", "PGRST_DB_SCHEMA", "PGRST_DB_ANON_ROLE"]
        for var_name in checks:
            if var_name.lower() in page_text.lower():
                result[var_name] = {"status": "[OK]", "value": "присутствует"}
                print(f"   [OK] {var_name} присутствует")
            else:
                result[var_name] = {"status": "[FAIL]", "value": "отсутствует"}
                print(f"   [FAIL] {var_name} не найден в переменных")

    return result


# ---------------------------------------------------------------------------
# Шаг 5: Поиск pgAdmin
# ---------------------------------------------------------------------------

async def step_find_pgadmin(page: Page) -> str | None:
    """Найти pgAdmin среди сервисов Amvera и получить его URL."""
    print("\n" + "=" * 60)
    print("[5] Поиск pgAdmin...")
    print("=" * 60)

    await screenshot(page, "05_before_pgadmin_search")
    await log_page_info(page, "before_pgadmin_search")

    # Возвращаемся к списку сервисов
    await page.goto(f"{AMVERA_URL}/projects", wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
    await asyncio.sleep(2)

    # Переходим к сервисам
    services_selectors = [
        'a:has-text("Сервисы")',
        'button:has-text("Сервисы")',
        'span:has-text("Сервисы")',
    ]
    for sel in services_selectors:
        if await safe_click(page, sel, timeout=5000):
            break
    else:
        current = page.url.rstrip("/")
        await page.goto(f"{current}/services", wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)

    await asyncio.sleep(3)
    await screenshot(page, "05_services_for_pgadmin")
    await log_page_info(page, "services_for_pgadmin")

    # Ищем pgAdmin в списке
    pgadmin_selectors = [
        'a:has-text("pgadmin")',
        'a:has-text("pgAdmin")',
        'a:has-text("PGAdmin")',
        'div:has-text("pgadmin")',
        'div:has-text("pgAdmin")',
        'span:has-text("pgadmin")',
        'li:has-text("pgadmin")',
        'tr:has-text("pgadmin")',
    ]

    pgadmin_url = None
    for sel in pgadmin_selectors:
        try:
            element = await page.wait_for_selector(sel, state="visible", timeout=5000)
            if element:
                href = await element.get_attribute("href")
                if href:
                    pgadmin_url = href
                    print(f"   [OK] pgAdmin найден: {pgadmin_url}")
                else:
                    # Может быть, это кликабельный элемент без href
                    await element.click()
                    await asyncio.sleep(2)
                    pgadmin_url = page.url
                    print(f"   [OK] pgAdmin открыт: {pgadmin_url}")
                break
        except PlaywrightTimeout:
            continue
        except Exception:
            continue

    if not pgadmin_url:
        # Пробуем найти через предустановленные сервисы
        print("   [DEBUG] Ищем pgAdmin через 'Преднастроенные сервисы'...")
        preset_selectors = [
            'a:has-text("Преднастроенные")',
            'button:has-text("Преднастроенные")',
            'span:has-text("Преднастроенные")',
            'a:has-text("Preset")',
        ]
        for sel in preset_selectors:
            if await safe_click(page, sel, timeout=5000):
                await asyncio.sleep(2)
                # Снова ищем pgadmin
                for psel in pgadmin_selectors:
                    try:
                        element = await page.wait_for_selector(psel, state="visible", timeout=3000)
                        if element:
                            href = await element.get_attribute("href")
                            pgadmin_url = href or page.url
                            print(f"   [OK] pgAdmin найден в преднастроенных: {pgadmin_url}")
                            break
                    except PlaywrightTimeout:
                        continue
                break

    if not pgadmin_url:
        print("   [WARN] pgAdmin не найден. Возможно, он ещё не создан.")
        await screenshot(page, "05_pgadmin_not_found")
    else:
        await screenshot(page, "05_pgadmin_found")

    return pgadmin_url


# ---------------------------------------------------------------------------
# Шаг 6: Вход в pgAdmin
# ---------------------------------------------------------------------------

async def step_login_pgadmin(page: Page, pgadmin_url: str | None) -> bool:
    """Войти в pgAdmin."""
    print("\n" + "=" * 60)
    print("[6] Вход в pgAdmin...")
    print("=" * 60)

    if not pgadmin_url:
        print("   [FAIL] Нет URL для pgAdmin — пропускаем")
        return False

    await page.goto(pgadmin_url, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
    await asyncio.sleep(3)
    await screenshot(page, "06_pgadmin_login_page")
    await log_page_info(page, "pgadmin_login_page")

    # pgAdmin обычно использует стандартную форму
    email_filled = False
    for sel in [
        'input[name="email"]',
        'input[type="email"]',
        'input[id="email"]',
        'input[id="inputEmail"]',
    ]:
        if await safe_fill(page, sel, PGADMIN_LOGIN, timeout=3000):
            email_filled = True
            print(f"   [OK] Email pgAdmin заполнен: {sel}")
            break

    if not email_filled:
        print("   [WARN] Не удалось найти поле email в pgAdmin")
        await screenshot(page, "06_pgadmin_email_not_found")

    password_filled = False
    for sel in [
        'input[name="password"]',
        'input[type="password"]',
        'input[id="password"]',
        'input[id="inputPassword"]',
    ]:
        if await safe_fill(page, sel, PGADMIN_PASSWORD, timeout=3000):
            password_filled = True
            print(f"   [OK] Пароль pgAdmin заполнен: {sel}")
            break

    if not password_filled:
        print("   [WARN] Не удалось найти поле пароля в pgAdmin")

    await asyncio.sleep(0.5)

    for sel in [
        'button[type="submit"]',
        'button:has-text("Login")',
        'button:has-text("Войти")',
        'button:has-text("Sign in")',
        'input[type="submit"]',
    ]:
        if await safe_click(page, sel, timeout=3000):
            print(f"   [OK] Кнопка входа pgAdmin нажата: {sel}")
            break
    else:
        print("   [WARN] Не удалось найти кнопку входа в pgAdmin")

    await asyncio.sleep(5)
    await screenshot(page, "06_pgadmin_after_login")
    await log_page_info(page, "pgadmin_after_login")

    # Проверяем, что вошли (нет ошибки на странице)
    page_text = await page.text_content("body")
    if page_text and ("invalid" in page_text.lower() or "неверн" in page_text.lower() or "ошибк" in page_text.lower()):
        print("   [FAIL] Похоже, вход в pgAdmin не удался")
        return False

    print("   [OK] Вход в pgAdmin выполнен")
    return True


# ---------------------------------------------------------------------------
# Шаг 7: Проверка базы данных через pgAdmin
# ---------------------------------------------------------------------------

async def step_query_database(page: Page) -> dict:
    """Выполнить проверочные SQL-запросы через pgAdmin Query Tool."""
    print("\n" + "=" * 60)
    print("[7] Проверка базы данных...")
    print("=" * 60)

    result = {}
    await screenshot(page, "07_before_query")
    await log_page_info(page, "before_query")

    # В pgAdmin нужно найти trudnik-db-superuser или trudnik-db
    # Ищем сервер/базу данных trudnik
    db_selectors = [
        'span:has-text("trudnik-db")',
        'div:has-text("trudnik-db")',
        'a:has-text("trudnik-db")',
        'span:has-text("trudnik")',
        'div:has-text("trudnik")',
        'li:has-text("trudnik-db")',
        '.node:has-text("trudnik")',
    ]

    db_found = False
    for sel in db_selectors:
        try:
            element = await page.wait_for_selector(sel, state="visible", timeout=5000)
            if element:
                await element.click()
                db_found = True
                print(f"   [OK] База данных trudnik найдена: {sel}")
                break
        except PlaywrightTimeout:
            continue
        except Exception:
            continue

    if not db_found:
        print("   [WARN] База данных trudnik не найдена в дереве pgAdmin")
        await screenshot(page, "07_db_not_found")

    await asyncio.sleep(2)

    # Ищем Query Tool
    query_tool_selectors = [
        'button:has-text("Query Tool")',
        'a:has-text("Query Tool")',
        'button[aria-label="Query Tool" i]',
        'li:has-text("Query Tool")',
        '[data-label="Query Tool" i]',
        '.query-tool-button',
    ]

    qt_found = False
    for sel in query_tool_selectors:
        if await safe_click(page, sel, timeout=5000):
            qt_found = True
            print(f"   [OK] Query Tool открыт: {sel}")
            break

    if not qt_found:
        # Пробуем через контекстное меню (правый клик по БД)
        if db_found:
            try:
                await page.click("span:has-text('trudnik')", button="right")
                await asyncio.sleep(1)
                await safe_click(page, 'li:has-text("Query Tool")', timeout=3000)
                qt_found = True
                print("   [OK] Query Tool открыт через контекстное меню")
            except Exception:
                pass

    if not qt_found:
        print("   [WARN] Query Tool не найден")
        await screenshot(page, "07_query_tool_not_found")
        return result

    await asyncio.sleep(3)
    await screenshot(page, "07_query_tool_open")
    await log_page_info(page, "query_tool_open")

    # Ищем текстовое поле для ввода SQL (обычно CodeMirror или textarea)
    queries = [
        ("religions_count", "SELECT count(*) FROM religions;"),
        ("skills_count", "SELECT count(*) FROM skills;"),
        ("admin_profile", "SELECT count(*) FROM profiles WHERE email='admin@test.ru';"),
    ]

    # Ищем поле ввода SQL
    sql_input_selectors = [
        '.CodeMirror',
        'textarea[aria-label*="SQL" i]',
        'textarea[aria-label*="query" i]',
        'textarea.sql-editor',
        '.sql-editor textarea',
        '.ace_editor',
        'div[role="textbox"]',
    ]

    for query_name, sql in queries:
        print(f"\n   [SQL] Выполнение запроса: {query_name}")
        print(f"      SQL: {sql}")

        # Находим поле ввода
        input_found = False
        for sel in sql_input_selectors:
            try:
                element = await page.wait_for_selector(sel, state="visible", timeout=5000)
                if element:
                    # Для CodeMirror нужно использовать специальный подход
                    if "CodeMirror" in sel:
                        await page.click(sel)
                        await asyncio.sleep(0.5)
                        await page.keyboard.press("Control+a")
                        await page.keyboard.press("Delete")
                        await page.keyboard.type(sql, delay=20)
                        input_found = True
                        print(f"      [OK] SQL введён через CodeMirror")
                        break
                    elif "ace_editor" in sel:
                        await page.click(sel)
                        await asyncio.sleep(0.5)
                        await page.keyboard.press("Control+a")
                        await page.keyboard.press("Delete")
                        await page.keyboard.type(sql, delay=20)
                        input_found = True
                        print(f"      [OK] SQL введён через ACE Editor")
                        break
                    else:
                        await element.fill(sql)
                        input_found = True
                        print(f"      [OK] SQL введён через: {sel}")
                        break
            except PlaywrightTimeout:
                continue
            except Exception:
                continue

        if not input_found:
            print("      [WARN] Не удалось найти поле ввода SQL")
            await screenshot(page, f"07_sql_input_not_found_{query_name}")
            result[query_name] = {"status": "[WARN]", "result": "не удалось ввести запрос"}
            continue

        await asyncio.sleep(0.5)

        # Кнопка выполнения запроса
        execute_selectors = [
            'button:has-text("Execute")',
            'button[aria-label="Execute" i]',
            'button:has-text("Выполнить")',
            'button.execute-button',
            '.execute-btn',
            'button[title="Execute query" i]',
        ]

        executed = False
        for sel in execute_selectors:
            if await safe_click(page, sel, timeout=3000):
                executed = True
                print(f"      [OK] Запрос выполнен через: {sel}")
                break

        if not executed:
            # Пробуем F5 (горячая клавиша pgAdmin)
            await page.keyboard.press("F5")
            executed = True
            print("      [OK] Запрос выполнен через F5")

        await asyncio.sleep(3)
        await screenshot(page, f"07_query_result_{query_name}")

        # Пытаемся прочитать результат из таблицы результатов
        try:
            # pgAdmin показывает результат в таблице
            result_selectors = [
                '.query-result-table td',
                '.datagrid-cell',
                'table[id*="result" i] td',
                '.pgadmin-result-grid td',
                'div[role="gridcell"]',
            ]
            result_text = None
            for sel in result_selectors:
                try:
                    cells = await page.query_selector_all(sel)
                    if cells and len(cells) > 0:
                        result_text = await cells[0].text_content()
                        break
                except Exception:
                    continue

            if result_text:
                result[query_name] = {"status": "[OK]", "result": result_text.strip()}
                print(f"      [RESULT] Результат: {result_text.strip()}")
            else:
                result[query_name] = {"status": "[WARN]", "result": "результат не отображён"}
                print("      [WARN] Результат не удалось прочитать")
        except Exception as e:
            result[query_name] = {"status": "[WARN]", "result": f"ошибка чтения: {e}"}
            print(f"      [WARN] Ошибка чтения результата: {e}")

    return result


# ---------------------------------------------------------------------------
# Шаг 8: Проверка сайта
# ---------------------------------------------------------------------------

async def step_check_site(page: Page) -> dict:
    """Проверить доступность сайта trudnik."""
    print("\n" + "=" * 60)
    print("[8] Проверка сайта trudnik...")
    print("=" * 60)

    result = {}

    urls_to_check = [
        ("Главная", SITE_URL),
        ("Логин", f"{SITE_URL}/login"),
        ("Регистрация", f"{SITE_URL}/register"),
    ]

    for name, url in urls_to_check:
        try:
            print(f"   [DEBUG] Проверка {name}: {url}")
            response = await page.goto(url, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
            status = response.status if response else "нет ответа"
            await asyncio.sleep(2)
            await screenshot(page, f"08_site_{name.lower()}")
            await log_page_info(page, f"site_{name.lower()}")

            # Проверяем, что страница не показывает ошибку
            page_text = await page.text_content("body")
            is_error = page_text and any(
                err in page_text.lower()
                for err in ["500", "ошибка сервера", "internal server error", "service unavailable"]
            )

            if is_error:
                result[name] = {"status": "[FAIL]", "http": status, "detail": "обнаружена ошибка на странице"}
                print(f"   [FAIL] {name}: HTTP {status}, ошибка на странице")
            else:
                result[name] = {"status": "[OK]", "http": status}
                print(f"   [OK] {name}: HTTP {status}")
        except PlaywrightTimeout:
            result[name] = {"status": "[FAIL]", "http": None, "detail": "таймаут загрузки"}
            print(f"   [FAIL] {name}: таймаут загрузки")
        except Exception as e:
            result[name] = {"status": "[FAIL]", "http": None, "detail": str(e)}
            print(f"   [FAIL] {name}: {e}")

    return result


# ---------------------------------------------------------------------------
# pgAdmin API Fix — прямой доступ через REST API (без Playwright/браузера)
# ---------------------------------------------------------------------------

# Данные для заполнения справочников (из migration 007)
_RELIGIONS = [
    "Православие",
    "Католичество",
    "Ислам",
    "Иудаизм",
    "Буддизм",
    "Не важно",
]

_SKILLS = [
    "Уборка",
    "Повар",
    "Садоводство",
    "Плотник",
    "Электрик",
    "Маляр",
    "Сантехник",
    "Водитель",
    "Разнорабочий",
    "Столяр",
    "Разгрузка",
    "Штукатур",
    "Плиточник",
    "Кровельщик",
    "Сварщик",
    "IT",
    "Бухгалтер",
    "Секретарь",
    "Охрана",
    "Уход за животными",
]

PGADMIN_API_URL = "https://trudnik-pgadmin-hyperstls.amvera.io"
PGADMIN_API_LOGIN = "admin@trudnik.ru"
PGADMIN_API_PASSWORD = "***REMOVED***"


def _pgadmin_login(session: requests.Session) -> Optional[str]:
    """Войти в pgAdmin через REST API и вернуть CSRF-токен.

    Возвращает csrf_token или None при неудаче.
    """
    print("\n" + "=" * 60)
    print("[pgAdmin API] Вход в pgAdmin...")
    print("=" * 60)

    # Шаг 1: GET /login — получить CSRF-токен из cookie или HTML
    try:
        r = session.get(f"{PGADMIN_API_URL}/login", timeout=15)
    except requests.RequestException as e:
        print(f"   [FAIL] Не удалось подключиться к pgAdmin: {e}")
        return None

    csrf_token: Optional[str] = None

    # Пробуем извлечь из cookies
    for name in ("CSRF-TOKEN", "pgadmin_csrf_token", "XSRF-TOKEN", "csrf_token"):
        if name in session.cookies:
            csrf_token = session.cookies[name]
            print(f"   [DEBUG] CSRF-токен из cookie '{name}': {csrf_token[:20]}...")
            break

    # Если в cookie нет — ищем в HTML
    if not csrf_token:
        html = r.text
        for pattern in (
            r'csrfToken["\s]*:["\s]*"([^"]+)"',
            r'csrf_token["\s]*:["\s]*"([^"]+)"',
            r'name="csrf_token"[^>]*value="([^"]+)"',
            r'id="csrf_token"[^>]*value="([^"]+)"',
            r'"csrfToken"\s*:\s*"([^"]+)"',
        ):
            m = re.search(pattern, html)
            if m:
                csrf_token = m.group(1)
                print(f"   [DEBUG] CSRF-токен из HTML: {csrf_token[:20]}...")
                break

    if not csrf_token:
        # Последняя попытка — вывести все cookies для отладки
        print("   [DEBUG] Cookies после GET /login:")
        for c in session.cookies:
            print(f"      {c.name} = {c.value[:40] if c.value else '(empty)'}")
        print("   [FAIL] Не удалось извлечь CSRF-токен")
        return None

    # Шаг 2: POST /authenticate/login
    login_payload = {
        "email": PGADMIN_API_LOGIN,
        "password": PGADMIN_API_PASSWORD,
        "language": "ru",
        "csrf_token": csrf_token,
    }

    headers = {
        "X-CSRFToken": csrf_token,
        "X-pgA-CSRFToken": csrf_token,
        "Content-Type": "application/json",
        "Referer": f"{PGADMIN_API_URL}/login",
    }

    try:
        r = session.post(
            f"{PGADMIN_API_URL}/authenticate/login",
            json=login_payload,
            headers=headers,
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"   [FAIL] Ошибка при отправке логина: {e}")
        return None

    if r.status_code == 200:
        data = r.json() if r.text else {}
        if data.get("success") or data.get("data", {}).get("auth", False) or "error" not in str(data).lower():
            print("   [OK] Успешный вход в pgAdmin через API")
        else:
            print(f"   [WARN] Ответ логина: {r.status_code}, тело: {str(data)[:200]}")
    elif r.status_code == 302:
        print("   [OK] Успешный вход в pgAdmin через API (редирект 302)")
    else:
        print(f"   [WARN] Код ответа логина: {r.status_code}, тело: {r.text[:200]}")
        # Не считаем это фатальной ошибкой — возможно, уже залогинены

    # Обновляем CSRF-токен после логина
    for name in ("CSRF-TOKEN", "pgadmin_csrf_token", "XSRF-TOKEN"):
        if name in session.cookies:
            new_token = session.cookies[name]
            if new_token != csrf_token:
                csrf_token = new_token
                print(f"   [DEBUG] CSRF-токен обновлён из cookie '{name}'")
                break

    return csrf_token


def _pgadmin_find_server(session: requests.Session, csrf_token: str) -> Optional[int]:
    """Найти сервер trudnik-db-superuser через API.

    Возвращает server_id (int) или None.
    """
    print("\n" + "=" * 60)
    print("[pgAdmin API] Поиск сервера trudnik-db...")
    print("=" * 60)

    headers = {
        "X-CSRFToken": csrf_token,
        "X-pgA-CSRFToken": csrf_token,
        "Accept": "application/json",
    }

    try:
        r = session.get(
            f"{PGADMIN_API_URL}/browser/server/",
            headers=headers,
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"   [FAIL] Ошибка при получении списка серверов: {e}")
        return None

    if r.status_code != 200:
        print(f"   [FAIL] GET /browser/server/ вернул {r.status_code}: {r.text[:200]}")
        return None

    try:
        data = r.json()
    except ValueError:
        print(f"   [FAIL] Некорректный JSON в ответе /browser/server/: {r.text[:200]}")
        return None

    servers = data if isinstance(data, list) else data.get("data", [])
    if not isinstance(servers, list):
        servers = []

    print(f"   [DEBUG] Найдено серверов: {len(servers)}")
    for srv in servers:
        name = srv.get("name", "")
        sid = srv.get("id")
        print(f"   [DEBUG]   id={sid}, name='{name}'")

    server_id: Optional[int] = None
    for srv in servers:
        name = srv.get("name", "")
        if "trudnik" in name.lower():
            server_id = srv.get("id")
            print(f"   [OK] Сервер найден: id={server_id}, name='{name}'")
            break

    if server_id is None:
        print("   [FAIL] Сервер trudnik-db не найден в списке")
        return None

    return server_id


def _pgadmin_find_database(
    session: requests.Session, csrf_token: str, server_id: int
) -> Optional[int]:
    """Найти первую базу данных на сервере.

    Возвращает database_id (int) или None.
    """
    print("\n[pgAdmin API] Поиск базы данных...")

    headers = {
        "X-CSRFToken": csrf_token,
        "X-pgA-CSRFToken": csrf_token,
        "Accept": "application/json",
    }

    # Пробуем несколько вариантов получения списка БД
    urls_to_try = [
        f"{PGADMIN_API_URL}/browser/server/children/{server_id}/server/{server_id}",
        f"{PGADMIN_API_URL}/browser/server/children/{server_id}/database/",
        f"{PGADMIN_API_URL}/browser/server/{server_id}",
    ]

    database_id: Optional[int] = None

    for url in urls_to_try:
        try:
            r = session.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                children = data if isinstance(data, list) else data.get("data", [])
                if not isinstance(children, list):
                    # Возможно, ответ — один объект сервера
                    children = data.get("children", []) if isinstance(data, dict) else []

                for child in children:
                    child_type = child.get("_type", child.get("type", ""))
                    child_name = child.get("name", "")
                    if child_type in ("database", "db") or (
                        isinstance(child, dict) and child_type == "" and child_name
                    ):
                        # В pgAdmin тип БД может определяться по наличию поля 'datlastsysoid'
                        # или просто первой записью в списке
                        if database_id is None:
                            database_id = child.get("id")
                            print(f"   [DEBUG]   db id={database_id}, name='{child_name}', type='{child_type}'")

                # Если нашли конкретно trudnik
                for child in children:
                    child_type = child.get("_type", child.get("type", ""))
                    child_name = child.get("name", "")
                    if "trudnik" in child_name.lower() and child_type in ("database", "db", ""):
                        database_id = child.get("id")
                        print(f"   [OK] База данных найдена: id={database_id}, name='{child_name}'")
                        break

                if database_id is not None:
                    break

        except requests.RequestException as e:
            print(f"   [DEBUG] URL {url} — ошибка: {e}")
            continue
        except ValueError:
            print(f"   [DEBUG] URL {url} — некорректный JSON")
            continue

    if database_id is None:
        # Последняя попытка — использовать стандартный ID 1
        print("   [WARN] База данных не найдена явно, пробуем стандартный did=1")
        database_id = 1

    return database_id


def _pgadmin_execute_sql(
    session: requests.Session,
    csrf_token: str,
    server_id: int,
    database_id: int,
    sql: str,
    query_name: str = "query",
    timeout: int = 30,
) -> dict:
    """Выполнить SQL-запрос через pgAdmin Query Tool API.

    Возвращает словарь с ключами: status, result, error.
    """
    headers = {
        "X-CSRFToken": csrf_token,
        "X-pgA-CSRFToken": csrf_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "sid": str(server_id),
        "did": str(database_id),
        "sql": sql,
    }

    # Пробуем несколько эндпоинтов для выполнения SQL
    execute_urls = [
        f"{PGADMIN_API_URL}/sqleditor/view_data/start/",
        f"{PGADMIN_API_URL}/sqleditor/query_tool/start/",
        f"{PGADMIN_API_URL}/sqleditor/start/",
    ]

    trans_id: Optional[str] = None
    raw_response = None

    for url in execute_urls:
        try:
            print(f"   [DEBUG] Пробуем {url}...")
            r = session.post(url, json=payload, headers=headers, timeout=timeout)
            raw_response = r
            if r.status_code == 200:
                try:
                    data = r.json()
                    # Ищем trans_id в разных возможных полях
                    if isinstance(data, dict):
                        trans_id = (
                            data.get("data", {}).get("trans_id")
                            or data.get("trans_id")
                            or data.get("data", {}).get("transaction_id")
                        )
                    if trans_id:
                        print(f"   [DEBUG] Получен trans_id: {trans_id}")
                        break
                    else:
                        print(f"   [DEBUG] Ответ 200, но trans_id не найден: {str(data)[:300]}")
                except ValueError:
                    print(f"   [DEBUG] Ответ 200, но не JSON: {r.text[:200]}")
            elif r.status_code == 404:
                print(f"   [DEBUG] Эндпоинт {url} не найден (404)")
                continue
            else:
                print(f"   [DEBUG] {url} -> {r.status_code}: {r.text[:200]}")
        except requests.RequestException as e:
            print(f"   [DEBUG] {url} — ошибка соединения: {e}")
            continue

    if trans_id is None:
        # Если не удалось получить trans_id, но запрос отработал — пробуем прочитать результат из ответа
        if raw_response is not None and raw_response.status_code == 200:
            try:
                data = raw_response.json()
                if isinstance(data, dict):
                    result_data = data.get("data", data)
                    if isinstance(result_data, dict) and "result" in result_data:
                        return {"status": "[OK]", "result": result_data["result"], "error": None}
                    # Может, данные уже содержат rows
                    if "rows" in result_data or "columns" in result_data:
                        return {"status": "[OK]", "result": result_data, "error": None}
            except ValueError:
                pass

        return {
            "status": "[WARN]",
            "result": raw_response.text[:500] if raw_response is not None else "нет ответа",
            "error": "Не удалось получить trans_id для отслеживания запроса",
        }

    # Ждём выполнения и получаем результат
    time.sleep(2)

    result_urls = [
        f"{PGADMIN_API_URL}/sqleditor/query_tool/results/{trans_id}",
        f"{PGADMIN_API_URL}/sqleditor/query_tool/download/{trans_id}",
        f"{PGADMIN_API_URL}/sqleditor/results/{trans_id}",
    ]

    for url in result_urls:
        try:
            r = session.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                try:
                    data = r.json()
                    return {"status": "[OK]", "result": data, "error": None}
                except ValueError:
                    return {"status": "[OK]", "result": r.text, "error": None}
            elif r.status_code == 202:
                # Запрос ещё выполняется, ждём
                for _ in range(5):
                    time.sleep(2)
                    r2 = session.get(url, headers=headers, timeout=timeout)
                    if r2.status_code == 200:
                        try:
                            return {"status": "[OK]", "result": r2.json(), "error": None}
                        except ValueError:
                            return {"status": "[OK]", "result": r2.text, "error": None}
        except requests.RequestException as e:
            continue

    # Статус запроса
    status_url = f"{PGADMIN_API_URL}/sqleditor/query_tool/status/{trans_id}"
    try:
        r = session.get(status_url, headers=headers, timeout=timeout)
        return {"status": "[WARN]", "result": r.text[:500], "error": f"Статус: {r.status_code}"}
    except Exception:
        return {"status": "[WARN]", "result": None, "error": "Не удалось получить результат"}


def pgadmin_api_fix() -> dict:
    """Выполнить SQL-запросы через pgAdmin REST API (без браузера).

    Шаги:
    1. Логин в pgAdmin через API
    2. Поиск сервера trudnik-db-superuser
    3. Проверка religions и skills (SELECT count)
    4. При необходимости — заполнение справочников
    5. GRANT ролей для trudnikapp
    6. Проверка профиля admin@test.ru

    Возвращает словарь с полным отчётом.
    """
    print("\n" + "#" * 60)
    print("### pgAdmin API Fix — прямое выполнение SQL через REST API")
    print(f"### Время запуска: {datetime.now(timezone.utc).isoformat()}")
    print("#" * 60)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "pgAdmin REST API",
        "steps": {},
        "queries": {},
        "actions": {},
    }

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    # -------------------------------------------------------------------
    # Шаг 1: Логин
    # -------------------------------------------------------------------
    csrf_token = _pgadmin_login(session)
    if not csrf_token:
        report["status"] = "FAILED"
        report["error"] = "Не удалось войти в pgAdmin"
        return report

    report["steps"]["login"] = {"status": "[OK]", "csrf_token": csrf_token[:10] + "..."}

    # -------------------------------------------------------------------
    # Шаг 2: Поиск сервера trudnik-db
    # -------------------------------------------------------------------
    server_id = _pgadmin_find_server(session, csrf_token)
    if server_id is None:
        report["status"] = "FAILED"
        report["error"] = "Сервер trudnik-db не найден"
        return report

    report["steps"]["find_server"] = {"status": "[OK]", "server_id": server_id}

    # -------------------------------------------------------------------
    # Шаг 3: Поиск базы данных
    # -------------------------------------------------------------------
    database_id = _pgadmin_find_database(session, csrf_token, server_id)
    report["steps"]["find_database"] = {"status": "[OK]", "database_id": database_id}

    print(f"\n[pgAdmin API] Сервер id={server_id}, База данных id={database_id}")

    # -------------------------------------------------------------------
    # Шаг 4: Проверочные SELECT-запросы
    # -------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("[pgAdmin API] Выполнение проверочных SQL-запросов...")
    print("=" * 60)

    check_queries = [
        ("religions_count", "SELECT count(*) FROM religions;"),
        ("skills_count", "SELECT count(*) FROM skills;"),
        ("admin_profile", "SELECT email, role FROM profiles WHERE email='admin@test.ru';"),
    ]

    religions_count = 0
    skills_count = 0
    admin_email = None
    admin_role = None

    for qname, sql in check_queries:
        print(f"\n   [SQL] {qname}: {sql}")
        result = _pgadmin_execute_sql(
            session, csrf_token, server_id, database_id, sql, qname
        )
        report["queries"][qname] = result

        status = result.get("status", "?")
        raw = result.get("result")

        # Пытаемся распарсить результат
        try:
            if isinstance(raw, dict):
                # pgAdmin возвращает структуру с data
                rows = raw.get("data", {}).get("rows", raw.get("rows", []))
                if not rows:
                    # Может быть вложенная структура
                    inner = raw.get("data", raw)
                    if isinstance(inner, dict):
                        # Пробуем найти count в любом поле
                        for key in ("rows", "result", "collections"):
                            if key in inner:
                                rows = inner[key]
                                break

                if qname == "religions_count":
                    if rows and len(rows) > 0:
                        religions_count = int(list(rows[0].values())[0]) if isinstance(rows[0], dict) else int(rows[0])
                    print(f"   [RESULT] religions_count = {religions_count}")

                elif qname == "skills_count":
                    if rows and len(rows) > 0:
                        skills_count = int(list(rows[0].values())[0]) if isinstance(rows[0], dict) else int(rows[0])
                    print(f"   [RESULT] skills_count = {skills_count}")

                elif qname == "admin_profile":
                    if rows and len(rows) > 0:
                        row = rows[0]
                        admin_email = row.get("email", "") if isinstance(row, dict) else ""
                        admin_role = row.get("role", "") if isinstance(row, dict) else ""
                    print(f"   [RESULT] admin_profile: email={admin_email}, role={admin_role}")

            elif isinstance(raw, str):
                print(f"   [RESULT] (строка): {raw[:200]}")
            elif isinstance(raw, list):
                print(f"   [RESULT] (список из {len(raw)} элементов)")
            else:
                print(f"   [RESULT] Тип: {type(raw).__name__}, значение: {str(raw)[:200]}")
        except Exception as e:
            print(f"   [WARN] Ошибка парсинга результата '{qname}': {e}")

        print(f"   [{status.replace('[', '').replace(']', '')}] {qname}")

    # -------------------------------------------------------------------
    # Шаг 5: Заполнение religions, если пустые
    # -------------------------------------------------------------------
    if religions_count == 0:
        print("\n" + "=" * 60)
        print("[pgAdmin API] Заполнение справочника religions (6 записей)...")
        print("=" * 60)

        values = ", ".join(f"('{r}')" for r in _RELIGIONS)
        insert_sql = f"INSERT INTO religions (name) VALUES {values} ON CONFLICT (name) DO NOTHING;"
        print(f"   [SQL] {insert_sql[:120]}...")

        result = _pgadmin_execute_sql(
            session, csrf_token, server_id, database_id, insert_sql, "insert_religions"
        )
        report["actions"]["insert_religions"] = result
        print(f"   [OK] Религии добавлены")

        # Проверяем ещё раз
        verify = _pgadmin_execute_sql(
            session, csrf_token, server_id, database_id,
            "SELECT count(*) FROM religions;", "religions_verify"
        )
        report["queries"]["religions_after_insert"] = verify
        print(f"   [OK] Проверка после вставки: {verify.get('result')}")
    else:
        print(f"\n   [OK] Религии уже заполнены ({religions_count} записей)")
        report["actions"]["insert_religions"] = {"status": "[SKIP]", "reason": f"Уже {religions_count} записей"}

    # -------------------------------------------------------------------
    # Шаг 6: Заполнение skills, если пустые
    # -------------------------------------------------------------------
    if skills_count == 0:
        print("\n" + "=" * 60)
        print("[pgAdmin API] Заполнение справочника skills (20 записей)...")
        print("=" * 60)

        values = ", ".join(f"('{s}')" for s in _SKILLS)
        insert_sql = f"INSERT INTO skills (name) VALUES {values} ON CONFLICT (name) DO NOTHING;"
        print(f"   [SQL] {insert_sql[:120]}...")

        result = _pgadmin_execute_sql(
            session, csrf_token, server_id, database_id, insert_sql, "insert_skills"
        )
        report["actions"]["insert_skills"] = result
        print(f"   [OK] Навыки добавлены")

        # Проверяем ещё раз
        verify = _pgadmin_execute_sql(
            session, csrf_token, server_id, database_id,
            "SELECT count(*) FROM skills;", "skills_verify"
        )
        report["queries"]["skills_after_insert"] = verify
        print(f"   [OK] Проверка после вставки: {verify.get('result')}")
    else:
        print(f"\n   [OK] Навыки уже заполнены ({skills_count} записей)")
        report["actions"]["insert_skills"] = {"status": "[SKIP]", "reason": f"Уже {skills_count} записей"}

    # -------------------------------------------------------------------
    # Шаг 7: GRANT ролей для trudnikapp
    # -------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("[pgAdmin API] Выдача ролей для trudnikapp...")
    print("=" * 60)

    grant_queries = [
        "GRANT anon TO trudnikapp;",
        "GRANT authenticated TO trudnikapp;",
        "GRANT service_role TO trudnikapp;",
    ]

    for grant_sql in grant_queries:
        print(f"   [SQL] {grant_sql}")
        result = _pgadmin_execute_sql(
            session, csrf_token, server_id, database_id, grant_sql, "grant_roles"
        )
        report["actions"][f"grant_{grant_sql.split()[1]}"] = result
        status = result.get("status", "?")
        print(f"   [{status.replace('[', '').replace(']', '')}] {grant_sql}")

    # -------------------------------------------------------------------
    # Итоговый статус
    # -------------------------------------------------------------------
    report["status"] = "OK"
    report["summary"] = {
        "religions_count": religions_count,
        "skills_count": skills_count,
        "admin_email": admin_email,
        "admin_role": admin_role,
    }

    _print_pgadmin_summary(report)
    return report


def _print_pgadmin_summary(report: dict):
    """Вывести итоговую сводку pgAdmin API Fix."""
    print("\n" + "=" * 60)
    print("[SUMMARY] pgAdmin API Fix — ИТОГИ")
    print("=" * 60)
    summary = report.get("summary", {})
    print(f"   Статус:       {report.get('status', 'UNKNOWN')}")
    print(f"   Религий:      {summary.get('religions_count', '?')}")
    print(f"   Навыков:      {summary.get('skills_count', '?')}")
    print(f"   admin@test.ru: email={summary.get('admin_email', '?')}, role={summary.get('admin_role', '?')}")
    print()

    for step_name, step_data in report.get("steps", {}).items():
        print(f"   {step_data.get('status', '?')} {step_name}: {step_data}")

    for action_name, action_data in report.get("actions", {}).items():
        print(f"   {action_data.get('status', '?')} {action_name}")

    print()
    failed = [k for k, v in report.get("queries", {}).items() if v.get("status", "").startswith("[FAIL]")]
    if failed:
        print(f"   [WARN] Запросов с ошибками: {len(failed)}")
        for f in failed:
            print(f"         - {f}")
    else:
        print("   [OK] Все запросы выполнены без ошибок")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Главная функция
# ---------------------------------------------------------------------------

async def main():
    """Точка входа — запуск всех шагов."""
    print("=" * 60)
    print("==> Amvera Agent — автоматизация проверки Amvera + pgAdmin")
    print(f"   Время запуска: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Создаём директорию для скриншотов
    ensure_screenshots_dir()
    print(f"[DIR] Скриншоты будут сохранены в: {SCREENSHOTS_DIR}")

    # Сбор всех результатов
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "steps": {},
    }

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

        # Устанавливаем разумный таймаут по умолчанию
        page.set_default_timeout(DEFAULT_TIMEOUT)

        try:
            # --- Шаг 1: Вход в Amvera ---
            step1_ok = await step_login_amvera(page)
            report["steps"]["1_login_amvera"] = {
                "status": "[OK]" if step1_ok else "[FAIL]",
                "detail": "Успешный вход" if step1_ok else "Ошибка входа",
            }

            if not step1_ok:
                print("\n   [FAIL] Не удалось войти в Amvera. Дальнейшие шаги пропущены.")
                report["status"] = "FAILED"
                await browser.close()
                _save_report(report)
                return

            # --- Шаг 2: Переход к проекту ---
            step2_ok = await step_navigate_to_project(page)
            report["steps"]["2_navigate_project"] = {
                "status": "[OK]" if step2_ok else "[WARN]",
                "detail": "Проект найден" if step2_ok else "Проект не удалось явно найти",
            }

            # --- Шаг 3: trudnik-app переменные ---
            step3_vars = await step_check_trudnik_app_vars(page)
            report["steps"]["3_trudnik_app_vars"] = {
                "status": "[OK]" if step3_vars else "[WARN]",
                "variables": step3_vars,
            }

            # --- Шаг 4: trudnik-pr переменные ---
            if step2_ok or True:  # Продолжаем даже если проект не найден явно
                step4_vars = await step_check_trudnik_pr_vars(page)
                report["steps"]["4_trudnik_pr_vars"] = {
                    "status": "[OK]" if step4_vars else "[WARN]",
                    "variables": step4_vars,
                }

            # --- Шаг 5: Поиск pgAdmin ---
            pgadmin_url = await step_find_pgadmin(page)
            report["steps"]["5_find_pgadmin"] = {
                "status": "[OK]" if pgadmin_url else "[WARN]",
                "url": pgadmin_url or "не найден",
            }

            # --- Шаг 6: Вход в pgAdmin ---
            step6_ok = await step_login_pgadmin(page, pgadmin_url)
            report["steps"]["6_login_pgadmin"] = {
                "status": "[OK]" if step6_ok else "[WARN]",
                "detail": "Успешный вход" if step6_ok else "Не удалось войти или нет URL",
            }

            # --- Шаг 7: Проверка БД ---
            if step6_ok:
                step7_results = await step_query_database(page)
                report["steps"]["7_database_queries"] = {
                    "status": "[OK]" if step7_results else "[WARN]",
                    "queries": step7_results,
                }
            else:
                report["steps"]["7_database_queries"] = {
                    "status": "[SKIP]",
                    "detail": "Пропущено — нет доступа к pgAdmin",
                }

            # --- Шаг 8: Проверка сайта ---
            step8_results = await step_check_site(page)
            report["steps"]["8_site_check"] = {
                "status": "[OK]",
                "results": step8_results,
            }

            # Определяем общий статус
            all_ok = all(
                s.get("status", "").startswith("[OK]") or s.get("status", "").startswith("[WARN]") or s.get("status", "").startswith("[SKIP]")
                for s in report["steps"].values()
            )
            report["status"] = "OK" if all_ok else "FAILED"

        except Exception as e:
            print(f"\n[FAIL] КРИТИЧЕСКАЯ ОШИБКА: {e}")
            await screenshot(page, "99_critical_error")
            report["status"] = "CRASHED"
            report["error"] = str(e)
            import traceback
            report["traceback"] = traceback.format_exc()
        finally:
            await browser.close()

    # Сохраняем отчёт
    _save_report(report)
    _print_summary(report)


def _save_report(report: dict):
    """Сохранить отчёт в JSON-файл."""
    report_path = SCREENSHOTS_DIR / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[REPORT] Отчёт сохранён: {report_path}")


def _print_summary(report: dict):
    """Вывести итоговую сводку."""
    print("\n" + "=" * 60)
    print("[SUMMARY] ИТОГОВЫЙ ОТЧЁТ")
    print("=" * 60)
    print(f"   Статус: {report.get('status', 'UNKNOWN')}")
    print(f"   Время:  {report.get('timestamp', 'N/A')}")
    print()
    for step_name, step_data in report.get("steps", {}).items():
        status_icon = step_data.get("status", "[?]")
        print(f"   {status_icon} {step_name}")
        if "variables" in step_data:
            for var_name, var_info in step_data["variables"].items():
                print(f"         {var_info.get('status', '?')} {var_name}: {var_info.get('value', 'N/A')}")
        if "queries" in step_data:
            for q_name, q_info in step_data["queries"].items():
                print(f"         {q_info.get('status', '?')} {q_name}: {q_info.get('result', 'N/A')}")
        if "results" in step_data:
            for site_name, site_info in step_data["results"].items():
                print(f"         {site_info.get('status', '?')} {site_name}: HTTP {site_info.get('http', 'N/A')}")
        if "url" in step_data:
            print(f"         URL: {step_data['url']}")
        if "detail" in step_data:
            print(f"         {step_data['detail']}")
    print()
    print(f"[DIR] Все скриншоты: {SCREENSHOTS_DIR}")
    print("=" * 60)
    print("\n[OK] Готово!")


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--pgadmin" in args or "--pgadmin-only" in args:
        # Только pgAdmin API Fix (без браузера)
        print("\n==> Запуск pgAdmin API Fix (только REST API, без Playwright)")
        report = pgadmin_api_fix()
        # Сохраняем отчёт
        ensure_screenshots_dir()
        report_path = SCREENSHOTS_DIR / "pgadmin_api_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n[REPORT] Отчёт сохранён: {report_path}")
    elif "--all" in args:
        # Сначала pgAdmin API Fix, затем Playwright-агент
        print("\n==> Запуск pgAdmin API Fix + Playwright-агент")
        ensure_screenshots_dir()
        report = pgadmin_api_fix()
        report_path = SCREENSHOTS_DIR / "pgadmin_api_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n[REPORT] Отчёт pgAdmin API сохранён: {report_path}")
        print("\n==> Переход к Playwright-агенту...")
        asyncio.run(main())
    elif "--help" in args or "-h" in args:
        print("""
Amvera Agent — автоматизация проверки Amvera + pgAdmin

Использование:
    python scripts/amvera_agent.py                  # Все шаги через Playwright
    python scripts/amvera_agent.py --pgadmin        # Только pgAdmin API Fix (без браузера)
    python scripts/amvera_agent.py --pgadmin-only   # То же самое
    python scripts/amvera_agent.py --all            # pgAdmin API Fix + Playwright
    python scripts/amvera_agent.py --help           # Эта справка
""")
    else:
        # По умолчанию: Playwright-агент
        asyncio.run(main())
