import sys
import json
import requests
from playwright.sync_api import sync_playwright

DEEPSEEK_API_KEY = "sk-4192af6e581549b58d35cedb5b8743b5"
BASE_URL = "https://trudnik.onrender.com"   # или ваш PythonAnywhere URL

def get_test_scenarios():
    """Просит DeepSeek сгенерировать тестовые сценарии для «Трудника»."""
    prompt = f"""
    Ты тестировщик веб-приложения «Трудник» (поиск подработки в храмах).
    Напиши список из 10-15 конкретных тестовых сценариев на русском языке,
    которые покрывают регистрацию, вход, создание задания, отклик, чат, смены, избранное.
    Каждый сценарий должен описывать действие и ожидаемый результат.
    Формат ответа – JSON-массив строк, например:
    ["Сценарий 1", "Сценарий 2", ...]
    """
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 500
    }
    resp = requests.post("https://api.deepseek.com/v1/chat/completions",
                         headers=headers, json=payload)
    if resp.ok:
        try:
            content = resp.json()["choices"][0]["message"]["content"]
            # Очищаем возможные markdown-обёртки
            if "```" in content:
                content = content.split("```")[1].strip()
                if content.startswith("json"):
                    content = content[4:].strip()
            scenarios = json.loads(content)
            return scenarios if isinstance(scenarios, list) else []
        except:
            return ["Ошибка парсинга ответа от DeepSeek"]
    return []

def run_tests(scenarios):
    """Запускает сценарии в браузере и выводит результат."""
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=True для фонового режима
        page = browser.new_page()
        for i, scenario in enumerate(scenarios, 1):
            print(f"🔹 Тест {i}: {scenario}")
            page.goto(BASE_URL)
            page.wait_for_timeout(1000)  # имитация загрузки
            # Здесь можно добавить реальные проверки, пока просто записываем сценарий
            results.append((i, scenario, "✅ Пройден (имитация)"))
        browser.close()
    return results

if __name__ == "__main__":
    print("🤖 Генерация тестовых сценариев через DeepSeek...")
    tests = get_test_scenarios()
    if not tests:
        print("❌ Не удалось получить сценарии. Проверьте API-ключ.")
        sys.exit(1)

    print(f"📋 Получено {len(tests)} сценариев:")
    for t in tests:
        print(f" - {t}")

    print("\n🚀 Запуск тестов в браузере...")
    report = run_tests(tests)

    print("\n📊 Отчёт:")
    for num, desc, status in report:
        print(f"{num:2}. {desc} → {status}")