"""
Браузерный агент для тестирования сайта Трудник через DeepSeek API и Playwright.

Два режима работы:
1. Сценарный:   python browser_agent.py --scenario admin|employer|worker|all
2. Командный:   python browser_agent.py "Твоя команда на русском"

Сценарии:
- admin:     вход как admin@test.ru, проверка админ-панели, выход
- employer:  вход как org@test.ru, проверка страницы "Мои задания", выход
- worker:    вход как trud@test.ru, проверка главной страницы, выход
- all:       последовательный прогон всех трёх ролей

Требуется: pip install openai playwright && playwright install chromium
"""

import sys
import json
import time
import argparse
from openai import OpenAI
from playwright.sync_api import sync_playwright

# ═══════════════════════════════════════════════════════════
# Конфигурация
# ═══════════════════════════════════════════════════════════
BASE_URL = "https://trudnik-hyperstls.amvera.io"

# DeepSeek API
client = OpenAI(
    api_key="sk-4192af6e581549b58d35cedb5b8743b5",
    base_url="https://api.deepseek.com/v1"
)

# Тестовые пользователи (после работы manage_users.py)
TEST_USERS = {
    "admin":    {"email": "admin@test.ru", "password": "Step@1986", "role": "admin"},
    "employer": {"email": "org@test.ru",   "password": "Step@1986", "role": "employer"},
    "worker":   {"email": "trud@test.ru",  "password": "Step@1986", "role": "worker"},
}

# ═══════════════════════════════════════════════════════════
# Сценарии тестирования
# ═══════════════════════════════════════════════════════════

SCENARIOS = {
    "admin": [
        f"Нажми на кнопку «Войти» или ссылку с текстом Войти",
        f"Заполни поле email значением {TEST_USERS['admin']['email']}",
        f"Заполни поле пароля значением {TEST_USERS['admin']['password']}",
        "Нажми на кнопку «Войти» в форме логина",
        "Подожди 2 секунды. Проверь, что на странице есть «Админ-панель» или «admin» — значит вход успешен.",
        "Нажми на кнопку «Выйти» или ссылку Выйти",
        "Подожди 2 секунды. Проверь, что появилась кнопка «Войти» — значит выход успешен.",
    ],
    "employer": [
        "Нажми на кнопку «Войти» или ссылку с текстом Войти",
        f"Заполни поле email значением {TEST_USERS['employer']['email']}",
        f"Заполни поле пароля значением {TEST_USERS['employer']['password']}",
        "Нажми на кнопку «Войти» в форме логина",
        "Подожди 2 секунды. Проверь, что на странице есть «Мои задания» или «Создать задание» — значит вход успешен.",
        "Нажми на кнопку «Выйти» или ссылку Выйти",
        "Подожди 2 секунды. Проверь, что появилась кнопка «Войти» — значит выход успешен.",
    ],
    "worker": [
        "Нажми на кнопку «Войти» или ссылку с текстом Войти",
        f"Заполни поле email значением {TEST_USERS['worker']['email']}",
        f"Заполни поле пароля значением {TEST_USERS['worker']['password']}",
        "Нажми на кнопку «Войти» в форме логина",
        "Подожди 2 секунды. Проверь, что видна главная страница с заданиями или появилось имя пользователя — значит вход успешен.",
        "Нажми на кнопку «Выйти» или ссылку Выйти",
        "Подожди 2 секунды. Проверь, что появилась кнопка «Войти» — значит выход успешен.",
    ],
}


def ask_deepseek(prompt: str) -> str:
    """Отправить вопрос в DeepSeek и вернуть ответ."""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Ошибка DeepSeek API: {e}")
        return '{"action": "done", "message": "DeepSeek API error"}'

def execute_scenario(role: str) -> dict:
    """
    Выполнить сценарий входа/выхода для заданной роли.
    Возвращает словарь с результатами.
    """
    if role not in TEST_USERS:
        return {"role": role, "success": False, "error": f"Неизвестная роль: {role}"}

    user = TEST_USERS[role]
    commands = SCENARIOS.get(role, [])
    if not commands:
        return {"role": role, "success": False, "error": "Нет сценария"}

    print(f"\n{'='*60}")
    print(f"🎭 Сценарий: {role.upper()} ({user['email']})")
    print(f"{'='*60}")

    results = {
        "role": role,
        "email": user["email"],
        "success": True,
        "steps": [],
        "login_success": False,
        "logout_success": False,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": 1280, "height": 800})

        try:
            page.goto(BASE_URL)
            page.wait_for_timeout(3000)
            print(f"   📄 Открыт: {page.url}")

            for i, command in enumerate(commands):
                print(f"\n   🔹 Шаг {i+1}/{len(commands)}: {command[:80]}...")

                # Получаем фрагмент HTML
                html_snippet = page.content()[:4000]

                prompt = f"""
Ты — браузерный агент, который управляет веб-сайтом «Трудник».
Сейчас ты на странице: {page.url}
HTML-код (фрагмент): {html_snippet}

Выполни команду пользователя: "{command}"

Верни ОДИН JSON-объект (без текста до или после):
{{
    "action": "click", "fill", "goto" или "done",
    "selector": "CSS-селектор элемента (если нужно)",
    "value": "текст для ввода (если fill)",
    "message": "что было сделано или ошибка"
}}

ВАЖНО: для кнопки «Войти» используй селектор: a.nav-link[href*="login"], .btn-primary, button:has-text("Войти"), a:has-text("Войти")
Для полей ввода: input[name="email"], input[type="email"], input[name="password"], input[type="password"]
Для кнопки отправки формы: button[type="submit"], button:has-text("Войти"), input[type="submit"]
Для кнопки «Выйти»: a[href*="logout"], a:has-text("Выйти"), button:has-text("Выйти")
"""
                ai_response = ask_deepseek(prompt)
                print(f"   🤖 DeepSeek: {ai_response[:200]}")

                # Парсим JSON
                try:
                    # Извлекаем JSON из ответа (может быть с лишним текстом)
                    json_match = None
                    for line in ai_response.split('\n'):
                        line = line.strip()
                        if line.startswith('{') and line.endswith('}'):
                            json_match = line
                            break
                    if not json_match:
                        # Ищем JSON в тексте
                        import re
                        m = re.search(r'\{[^{}]*\}', ai_response)
                        if m:
                            json_match = m.group(0)

                    if not json_match:
                        print(f"   ⚠️  Не удалось извлечь JSON, пробуем весь ответ")
                        json_match = ai_response

                    action_data = json.loads(json_match)
                except json.JSONDecodeError:
                    print(f"   ❌ Не удалось распарсить JSON. Пропускаем шаг.")
                    results["steps"].append({"step": i+1, "command": command, "success": False, "error": "JSON parse error"})
                    results["success"] = False
                    continue

                action = action_data.get("action", "done")
                selector = action_data.get("selector", "")
                value = action_data.get("value", "")
                message = action_data.get("message", "")

                print(f"   🎯 Действие: {action}, селектор: {selector[:60] if selector else '—'}")

                step_result = {"step": i+1, "command": command, "action": action, "message": message, "success": True}

                try:
                    if action == "click":
                        if selector:
                            page.wait_for_selector(selector, timeout=5000, state="visible")
                            page.click(selector)
                        else:
                            print(f"   ⚠️  Нет селектора для click")
                            step_result["success"] = False
                        page.wait_for_timeout(1500)
                    elif action == "fill":
                        if selector:
                            page.wait_for_selector(selector, timeout=5000, state="visible")
                            page.fill(selector, value)
                        else:
                            print(f"   ⚠️  Нет селектора для fill")
                            step_result["success"] = False
                    elif action == "goto":
                        page.goto(value if value else BASE_URL)
                        page.wait_for_timeout(3000)
                    elif action == "done":
                        pass
                    else:
                        print(f"   ⚠️  Неизвестное действие: {action}")
                        step_result["success"] = False
                except Exception as e:
                    print(f"   ❌ Ошибка выполнения: {e}")
                    step_result["success"] = False
                    step_result["error"] = str(e)[:150]

                results["steps"].append(step_result)

                # Проверяем признаки успешного входа/выхода
                if i == len(commands) - 2:  # предпоследний шаг — проверка входа
                    page_source = page.content()
                    if role == "admin":
                        results["login_success"] = "admin" in page_source.lower() or "админ-панель" in page_source.lower()
                    elif role == "employer":
                        results["login_success"] = "мои задания" in page_source.lower() or "создать задание" in page_source.lower()
                    elif role == "worker":
                        results["login_success"] = "трудник" in page_source.lower() or "задания" in page_source.lower()

                if i == len(commands) - 1:  # последний шаг — проверка выхода
                    page_source = page.content()
                    results["logout_success"] = "вход" in page_source.lower() and "logout" not in page.url.lower()

                time.sleep(0.5)

            # Финальный скриншот
            page.screenshot(path=f"test_{role}_final.png")
            print(f"\n   📸 Скриншот сохранён: test_{role}_final.png")

        except Exception as e:
            print(f"   ❌ Критическая ошибка: {e}")
            results["success"] = False
            results["error"] = str(e)
        finally:
            browser.close()

    return results


def execute_command(command: str):
    """Выполнить произвольную команду через DeepSeek + Playwright."""
    print(f"\n{'='*60}")
    print(f"🤖 Команда: {command}")
    print(f"{'='*60}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_viewport_size({"width": 1280, "height": 800})

        try:
            page.goto(BASE_URL)
            page.wait_for_timeout(3000)

            for step_num in range(10):  # максимум 10 шагов
                html_snippet = page.content()[:4000]

                prompt = f"""
Ты — браузерный агент, который управляет веб-сайтом «Трудник».
Сейчас ты на странице: {page.url}
HTML-код (фрагмент): {html_snippet}

Выполни команду пользователя: "{command}"

Верни ОДИН JSON-объект:
{{
    "action": "click", "fill", "goto" или "done",
    "selector": "CSS-селектор элемента (если нужно)",
    "value": "текст для ввода (если fill)",
    "message": "что было сделано или ошибка"
}}

Если команда выполнена полностью, верни action=done.
"""
                ai_response = ask_deepseek(prompt)
                print(f"🤖 DeepSeek [{step_num+1}]: {ai_response[:200]}")

                try:
                    action_data = json.loads(ai_response)
                except json.JSONDecodeError:
                    import re
                    m = re.search(r'\{[^{}]*\}', ai_response)
                    if m:
                        action_data = json.loads(m.group(0))
                    else:
                        print("❌ Не удалось распарсить JSON")
                        break

                action = action_data.get("action", "done")
                if action == "done":
                    print("✅ Команда выполнена")
                    break

                selector = action_data.get("selector", "")
                value = action_data.get("value", "")
                message = action_data.get("message", "")
                print(f"   🎯 {message}")

                try:
                    if action == "click" and selector:
                        page.wait_for_selector(selector, timeout=5000, state="visible")
                        page.click(selector)
                        page.wait_for_timeout(1500)
                    elif action == "fill" and selector:
                        page.wait_for_selector(selector, timeout=5000, state="visible")
                        page.fill(selector, value)
                    elif action == "goto":
                        page.goto(value if value else BASE_URL)
                        page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"   ❌ Ошибка: {e}")

        finally:
            browser.close()


def print_results(all_results: list[dict]):
    """Вывести сводку результатов тестирования."""
    print("\n" + "=" * 60)
    print("📊 СВОДКА РЕЗУЛЬТАТОВ ТЕСТИРОВАНИЯ")
    print("=" * 60)

    for r in all_results:
        role = r.get("role", "?")
        email = r.get("email", "?")
        login_ok = "✅" if r.get("login_success") else "❌"
        logout_ok = "✅" if r.get("logout_success") else "❌"
        overall = "✅ УСПЕХ" if r.get("success") and r.get("login_success") and r.get("logout_success") else "❌ ПРОВАЛ"

        print(f"\n{role.upper()} ({email})")
        print(f"   Вход:  {login_ok}")
        print(f"   Выход: {logout_ok}")
        print(f"   Итого: {overall}")

        if not r.get("success"):
            print(f"   Ошибка: {r.get('error', 'неизвестно')}")

    # Итоговая оценка
    all_ok = all(
        r.get("success") and r.get("login_success") and r.get("logout_success")
        for r in all_results
    )
    print(f"\n{'='*60}")
    if all_ok:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    else:
        print("⚠️  НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ. Проверьте логи выше.")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Браузерный агент для тестирования Трудник")
    parser.add_argument(
        "command",
        nargs="*",
        help="Команда на русском языке (если не указан --scenario)"
    )
    parser.add_argument(
        "--scenario", "-s",
        choices=["admin", "employer", "worker", "all"],
        help="Запустить готовый сценарий входа/выхода"
    )
    args = parser.parse_args()

    if args.scenario:
        # Сценарный режим
        if args.scenario == "all":
            roles = ["admin", "employer", "worker"]
        else:
            roles = [args.scenario]

        all_results = []
        for role in roles:
            result = execute_scenario(role)
            all_results.append(result)
            time.sleep(2)

        print_results(all_results)

    elif args.command:
        # Командный режим
        command = " ".join(args.command)
        execute_command(command)

    else:
        parser.print_help()
        print("\nПримеры:")
        print('  python browser_agent.py --scenario admin')
        print('  python browser_agent.py --scenario all')
        print('  python browser_agent.py "Зайди как admin@test.ru с паролем Step@1986 и проверь админ-панель"')


if __name__ == "__main__":
    main()
