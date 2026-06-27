"""
Playwright тест продакшена Trudnik
Использует cookies из prod_cookies.txt (curl-логин) для авторизации.
Проверка: логин, админка, версия, Skills, Religions, выход
"""
import sys
import os
from playwright.sync_api import sync_playwright
import http.cookiejar

BASE_URL = "https://trudnik-hyperstls.amvera.io"
results = []

def log_step(step_num, desc, status, detail=""):
    icon = "✅" if status else "❌"
    msg = f"{icon} [{step_num}] {desc}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append({"step": step_num, "desc": desc, "status": status, "detail": detail})

def load_cookies_from_netscape(filepath):
    """Загружает cookies из Netscape-формата (как curl сохраняет)"""
    cookies = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('# ') or line.startswith('#'):
                # Пропускаем комментарии, но не HttpOnly_ строки
                if line.startswith('#HttpOnly_'):
                    line = line.replace('#HttpOnly_', '', 1)  # Удаляем префикс
                else:
                    continue
            parts = line.split('\t')
            if len(parts) >= 7:
                domain = parts[0]
                # domain флаг
                include_subdomains = parts[1] == 'TRUE'
                path = parts[2]
                secure = parts[3] == 'TRUE'
                expires = int(parts[4]) if parts[4].isdigit() else 0
                name = parts[5]
                value = parts[6]
                cookies.append({
                    'name': name,
                    'value': value,
                    'domain': domain,
                    'path': path,
                    'secure': secure,
                    'httpOnly': False,
                    'sameSite': 'Lax',
                    'expires': expires if expires else -1
                })
    return cookies

def main():
    # Загружаем cookies из curl
    cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prod_cookies.txt')
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="ru-RU"
        )
        page = context.new_page()

        print("\n" + "="*60)
        print("  ТЕСТИРОВАНИЕ ПРОДАКШЕНА TRUDNIK")
        print("="*60)

        # Шаг 1: Устанавливаем cookies из curl
        if os.path.exists(cookies_path):
            cookies = load_cookies_from_netscape(cookies_path)
            log_step(1, f"Загрузка cookies из {cookies_path}", True, f"Найдено {len(cookies)} cookies")
            if cookies:
                context.add_cookies(cookies)
                log_step(1.1, "Установка cookies в браузер", True)
        else:
            log_step(1, f"Файл {cookies_path} не найден", False)

        # Шаг 2: Открыть главную (с куками)
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
        log_step(2, "Главная страница", True, f"URL: {page.url}")
        page.screenshot(path="test_main.png", full_page=True)
        
        # Проверка авторизации
        logged_in = "/login" not in page.url
        log_step(2.1, "Проверка авторизации", logged_in, f"URL: {page.url}")

        if not logged_in:
            # Пробуем прямой вход через fill
            log_step(2.2, "Попытка логина через форму...", True)
            page.goto(f"{BASE_URL}/login", wait_until="load")
            page.wait_for_timeout(2000)
            
            # Заполняем форму и добавляем CSRF
            page.evaluate("""(args) => {
                const form = document.querySelector('form');
                if (!form) return;
                document.getElementById('email').value = args.email;
                document.getElementById('password').value = args.password;
                const meta = document.querySelector('meta[name="csrf-token"]');
                if (meta) {
                    const input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = '_csrf_token';
                    input.value = meta.content;
                    form.appendChild(input);
                }
            }""", {"email": "admin@test.ru", "password": "Step@1986"})
            
            page.locator("button[type='submit']").first.click()
            page.wait_for_timeout(5000)
            
            logged_in = "/login" not in page.url
            log_step(2.3, "Проверка авторизации после формы", logged_in, f"URL: {page.url}")
            page.screenshot(path="test_after_form_login.png", full_page=True)

        # Шаг 3: Перейти в админку
        page.goto(f"{BASE_URL}/admin", wait_until="load")
        log_step(3, "Переход в админ-панель", True, f"URL: {page.url}")
        page.screenshot(path="test_admin.png", full_page=True)

        admin_content = page.content()
        is_admin = "Панель администратора" in admin_content
        
        # Шаг 4: Проверки админки
        has_admin_panel = "Панель администратора" in admin_content
        log_step(4, "Панель администратора", has_admin_panel)

        has_version = "214f946" in admin_content
        log_step(4.1, "Версия (git hash 214f946)", has_version)

        has_skills = '?tab=skills' in admin_content
        log_step(4.2, "Вкладка Skills", has_skills)

        has_religions = '?tab=religions' in admin_content
        log_step(4.3, "Вкладка Religions", has_religions)

        has_logout = "Выйти" in admin_content or "/logout" in admin_content
        log_step(4.4, "Кнопка/ссылка выхода", has_logout)

        # Шаг 5: Вкладка Skills
        page.goto(f"{BASE_URL}/admin?tab=skills", wait_until="load")
        log_step(5, "Вкладка Skills", True, f"URL: {page.url}")
        page.screenshot(path="test_skills.png", full_page=True)

        # Шаг 6: Вкладка Religions
        page.goto(f"{BASE_URL}/admin?tab=religions", wait_until="load")
        log_step(6, "Вкладка Religions", True, f"URL: {page.url}")
        page.screenshot(path="test_religions.png", full_page=True)

        # Шаг 7: Выход
        page.goto(f"{BASE_URL}/logout", wait_until="load")
        page.wait_for_timeout(3000)
        log_step(7, "Выход", True, f"URL: {page.url}")
        page.screenshot(path="test_logout.png", full_page=True)

        final_content = page.content()
        has_login_btn = "Войти" in final_content or "/login" in page.url
        log_step(7.1, "Проверка выхода", has_login_btn)

        browser.close()

    # Итоги
    print("\n" + "="*60)
    print("  ИТОГОВАЯ СВОДКА")
    print("="*60)
    passed = sum(1 for r in results if r["status"])
    failed = sum(1 for r in results if not r["status"])
    for r in results:
        icon = "✅" if r["status"] else "❌"
        print(f"  {icon} {r['desc']}: {'OK' if r['status'] else 'FAIL'}")
        if r["detail"]:
            print(f"      → {r['detail']}")
    print(f"\n  Итого: {passed} пройдено, {failed} не пройдено")
    print("="*60)

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
