import sys
import json
from openai import OpenAI
from playwright.sync_api import sync_playwright

# ⚙️ Настройки DeepSeek
client = OpenAI(
    api_key="sk-4192af6e581549b58d35cedb5b8743b5",   # ваш актуальный ключ
    base_url="https://api.deepseek.com/v1"
)

# 🔗 Адрес вашего сайта (можно заменить на PythonAnywhere-ссылку)
BASE_URL = "https://hyperstls.pythonanywhere.com"

def ask_deepseek(prompt):
    """Отправляем вопрос в DeepSeek и возвращаем ответ."""
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=500
    )
    return response.choices[0].message.content.strip()

def execute_command(command):
    """Выполняет одну команду: открывает сайт, отправляет контекст + команду в DeepSeek,
    получает действие и исполняет его через Playwright."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # False = показывать браузер
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_timeout(2000)  # ждём загрузки

        # Получаем фрагмент HTML-кода (первые 3000 символов)
        html_snippet = page.content()[:3000]

        prompt = f"""
You are a browser agent managing the "Trudnik" website.
Current page: {page.url}
HTML snippet: {html_snippet}

Execute user command: "{command}"

Return response in JSON format (use ONLY English keys and values):
{{
    "action": "click", "fill", "goto" or "done",
    "selector": "CSS selector (if needed)",
    "value": "text for input (if fill)",
    "message": "what was done or error message"
}}

If multiple actions needed, execute one at a time.
"""
        # Запрашиваем DeepSeek
        ai_response = ask_deepseek(prompt)
        print("[DEEPSEEK] Ответ received:", ai_response)

        # Пробуем распарсить JSON
        try:
            action_data = json.loads(ai_response)
        except Exception:
            print("[ERROR] Failed to parse DeepSeek response. Response:")
            print(ai_response)
            browser.close()
            return

        action = action_data.get("action")
        selector = action_data.get("selector")
        value = action_data.get("value")
        message = action_data.get("message", "")

        print(f"[INFO] {message}")

        # Выполняем действие
        try:
            if action == "click":
                page.click(selector)
                page.wait_for_timeout(1000)
            elif action == "fill":
                page.fill(selector, value)
            elif action == "goto":
                target_url = value if value else f"{BASE_URL}/job/new"
                page.goto(target_url)
                page.wait_for_timeout(2000)
            elif action == "done":
                pass
            else:
                print(f"[WARN] Unknown action: {action}")
        except Exception as e:
            print(f"[ERROR] Ошибка выполнения: {e}")

        browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python browser_agent.py \"Ваша команда\"")
        print("Пример: python browser_agent.py \"Зарегистрируй нового работника с именем Иван и паролем 123456\"")
        sys.exit(1)

    user_command = " ".join(sys.argv[1:])
    execute_command(user_command)