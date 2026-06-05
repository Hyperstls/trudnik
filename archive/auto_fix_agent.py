import os
import sys
import json
import requests
from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- Конфигурация ---
# Все секреты читаются из переменных окружения (файл .env)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

PA_USERNAME = os.getenv("PYTHONANYWHERE_USERNAME")
PA_API_TOKEN = os.getenv("PYTHONANYWHERE_API_TOKEN")

try:
    PA_CONSOLE_ID = int(os.getenv("PA_CONSOLE_ID", "0"))
except (ValueError, TypeError):
    raise RuntimeError(
        "PA_CONSOLE_ID должен быть целым числом. "
        "Проверьте файл .env"
    )

# Проверка обязательных переменных
_REQUIRED_ENV = {
    "DEEPSEEK_API_KEY": DEEPSEEK_API_KEY,
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_KEY,
    "PYTHONANYWHERE_USERNAME": PA_USERNAME,
    "PYTHONANYWHERE_API_TOKEN": PA_API_TOKEN,
    "PA_CONSOLE_ID": PA_CONSOLE_ID,
}
_missing = [k for k, v in _REQUIRED_ENV.items() if not v]
if _missing:
    raise RuntimeError(
        f"Отсутствуют обязательные переменные окружения: {', '.join(_missing)}. "
        f"Проверьте файл .env"
    )

# --- Клиенты ---
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json"
}

PA_HEADERS = {
    "Authorization": f"Token {PA_API_TOKEN}"
}

# --- Функции ---

def execute_sql(sql: str):
    """Выполняет SQL-запрос через REST API Supabase (RPC)."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/execute_sql"
    resp = requests.post(url, headers=SUPABASE_HEADERS, json={"sql": sql})
    if resp.status_code in (200, 201, 204):
        print(f"[OK] SQL выполнен успешно: {resp.text[:100]}")
    else:
        print(f"[ERROR] Ошибка SQL ({resp.status_code}): {resp.text[:200]}")

def git_pull_and_reload():
    """Отправляет команды git pull + reload в конкретную консоль PythonAnywhere."""
    send_cmd_url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/consoles/{PA_CONSOLE_ID}/send_input/"
    commands = "cd ~/mysite && git pull && touch /var/www/hyperstls_pythonanywhere_com_wsgi.py\n"
    resp = requests.post(send_cmd_url, headers=PA_HEADERS, json={"input": commands})
    if resp.status_code == 200:
        print("[OK] Команды git pull + reload отправлены в консоль. Сайт обновится через несколько секунд.")
        return True
    else:
        print(f"[ERROR] Ошибка отправки команд: {resp.status_code} {resp.text}")
        return False

def run_command(command):
    """Анализирует команду, при необходимости вызывает SQL или обновляет сайт."""
    prompt = f"""
Ты — помощник разработчика веб-приложения «Трудник» (Flask + Supabase).
Твоя задача: понять, что нужно сделать, и вернуть JSON-ответ.

Команда пользователя: {command}

Ответ должен быть в формате JSON:
{{
    "action": "sql" или "deploy" или "none",
    "details": "описание действия",
    "sql": "SQL-запрос (если action=sql)"
}}

Примеры:
- Если команда "добавь столбец verified в profiles", ответ: {{"action": "sql", "details": "добавление столбца", "sql": "ALTER TABLE profiles ADD COLUMN verified BOOLEAN DEFAULT false;"}}
- Если команда "обнови сайт", ответ: {{"action": "deploy", "details": "git pull и перезагрузка"}}
- Если команда не требует действий, ответ: {{"action": "none", "details": "ничего не делаем"}}
"""
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=300
    )
    content = response.choices[0].message.content.strip()
    if "```" in content:
        content = content.split("```")[1].strip()
        if content.startswith("json"):
            content = content[4:].strip()
    try:
        data = json.loads(content)
    except Exception:
        print("[ERROR] Не удалось распарсить ответ. Ответ:")
        print(content)
        return

    action = data.get("action")
    details = data.get("details", "")
    print(f"[INFO] {details}")

    if action == "sql":
        sql = data.get("sql", "")
        if sql:
            print("[SEND] Выполняю SQL...")
            execute_sql(sql)
        else:
            print("[WARN] Не указан SQL-запрос")
    elif action == "deploy":
        print("[UPDATE] Обновляю сайт...")
        git_pull_and_reload()
    else:
        print("[DONE] Действие не требуется")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python auto_fix_agent.py \"Ваша команда\"")
        sys.exit(1)
    user_cmd = " ".join(sys.argv[1:])
    run_command(user_cmd)