"""
Минимальный Playwright тест прода Trudnik
- Не ждёт полной загрузки страницы (domcontentloaded)
- Делает скриншоты
"""
import asyncio
from playwright.async_api import async_playwright

BASE_URL = "https://trudnik-hyperstls.amvera.io"
EMAIL = "admin@test.ru"
PASSWORD = "Step@1986"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage"
        ])
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        # Увеличиваем таймаут для навигации
        page.set_default_navigation_timeout(45000)
        page.set_default_timeout(45000)
        
        print("=" * 60)
        print("  PLAYWRIGHT ТЕСТ ПРОДАКШЕНА TRUDNIK")
        print("=" * 60)
        
        # 1. Открыть главную
        print("\n📄 1. Открываем главную страницу...")
        try:
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path="test_main_page.png", full_page=True)
            print("   ✅ Главная загружена, скриншот сохранён")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            # Даже если таймаут, делаем скриншот
            try:
                await page.screenshot(path="test_main_page.png", full_page=True)
                print("   ⚠️  Скриншот сделан (несмотря на ошибку)")
            except:
                print("   ❌ Не удалось сделать скриншот")
        
        # 2. Открыть страницу логина
        print("\n📄 2. Открываем страницу логина...")
        try:
            await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path="test_login_page.png", full_page=True)
            print("   ✅ Страница логина загружена")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            try:
                await page.screenshot(path="test_login_page.png", full_page=True)
            except:
                pass
        
        # 3. Логин через API (requests-like через fetch)
        print("\n📄 3. Выполняем логин через fetch API...")
        try:
            result = await page.evaluate("""
                async () => {
                    // Получаем CSRF токен
                    const html = await (await fetch('/login')).text();
                    const match = html.match(/<meta name="csrf-token" content="([^"]+)"/);
                    const csrf = match ? match[1] : '';
                    
                    // Логинимся
                    const resp = await fetch('/login', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'X-CSRF-Token': csrf
                        },
                        body: 'email=admin@test.ru&password=Step@1986&_csrf_token=' + encodeURIComponent(csrf),
                        redirect: 'follow'
                    });
                    return { status: resp.status, url: resp.url, ok: resp.ok };
                }
            """)
            print(f"   ✅ Логин: статус {result['status']}, URL: {result['url']}")
            
            # Делаем скриншот после логина
            await page.wait_for_timeout(3000)
            await page.screenshot(path="test_after_login.png", full_page=True)
        except Exception as e:
            print(f"   ❌ Ошибка логина: {e}")
        
        # 4. Перейти в админку
        print("\n📄 4. Открываем админку...")
        try:
            await page.goto(f"{BASE_URL}/admin", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
            await page.screenshot(path="test_admin_page.png", full_page=True)
            
            content = await page.content()
            
            checks = {
                "Панель администратора": "Панель администратора" in content,
                "Skills вкладка": '?tab=skills' in content,
                "Religions вкладка": '?tab=religions' in content,
                "Кнопка выхода": 'Выйти' in content or '/logout' in content,
                "Версия (214f946)": '214f946' in content
            }
            
            for name, ok in checks.items():
                print(f"   {'✅' if ok else '❌'} {name}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        # 5. Skills вкладка
        print("\n📄 5. Открываем Skills вкладку...")
        try:
            await page.goto(f"{BASE_URL}/admin?tab=skills", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path="test_skills_tab.png", full_page=True)
            print(f"   ✅ Skills вкладка: {await page.title()}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        # 6. Religions вкладка
        print("\n📄 6. Открываем Religions вкладку...")
        try:
            await page.goto(f"{BASE_URL}/admin?tab=religions", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path="test_religions_tab.png", full_page=True)
            print(f"   ✅ Religions вкладка: {await page.title()}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        # 7. Выход
        print("\n📄 7. Выполняем logout...")
        try:
            await page.goto(f"{BASE_URL}/logout", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path="test_after_logout.png", full_page=True)
            print("   ✅ Logout выполнен")
            
            # Проверяем что вышли
            await page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path="test_final_page.png", full_page=True)
            
            # Снова проверяем наличие кнопки Войти
            final_content = await page.content()
            has_login_btn = "Войти" in final_content
            print(f"   {'✅' if has_login_btn else '❌'} После выхода: кнопка Войти {'есть' if has_login_btn else 'отсутствует'}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        
        await browser.close()
        
        print("\n" + "=" * 60)
        print("  ТЕСТ ЗАВЕРШЁН")
        print("  Скриншоты: test_main_page.png, test_login_page.png,")
        print("  test_after_login.png, test_admin_page.png,")
        print("  test_skills_tab.png, test_religions_tab.png,")
        print("  test_after_logout.png, test_final_page.png")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
