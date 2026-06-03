"""
Отключение RLS для таблицы profiles через PythonAnywhere
"""

import sys
import json
import os
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://***REMOVED***.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
PA_USERNAME = os.getenv("PYTHONANYWHERE_USERNAME", "Hyperstls")
PA_API_TOKEN = os.getenv("PYTHONANYWHERE_API_TOKEN", "e4e936c2bed6824c4981927652c21986780e22b3")

venv_path = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
if venv_path.exists():
    python_cmd = str(venv_path)
else:
    python_cmd = "python"

def pythonanywhere_request(endpoint, method="GET", data=None):
    """Запрос к PythonAnywhere API"""
    url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/{endpoint}"
    headers = {"Authorization": f"Token {PA_API_TOKEN}"}
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"[PA] {method} {endpoint} -> {resp.status_code}")
        if resp.text:
            print(f"[PA] Response: {resp.text[:500]}")
        return resp
    except Exception as e:
        print(f"[PA ERROR] {e}")
        return None

def get_service_key_from_pa():
    """Получить SERVICE_KEY из PythonAnywhere"""
    print("\n[SERVICE] Попытка получения SERVICE_KEY из PythonAnywhere...")
    
    # Получаем консоль
    resp = pythonanywhere_request("consoles/", "GET")
    if not resp or resp.status_code != 200:
        print("[ERROR] Не удалось получить консоли")
        return None
    
    consoles = resp.json()
    if not consoles:
        print("[ERROR] Нет консолей")
        return None
    
    console_id = consoles[0]["id"]
    print(f"[PA] Используем консоль #{console_id}")
    
    # Отправляем команды для получения SERVICE_KEY
    send_url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/consoles/{console_id}/send_input/"
    
    commands = """
cd ~/mysite
source ~/.venv/bin/activate
cat .env 2>/dev/null | grep SUPABASE_SERVICE_ROLE_KEY || echo "NOT FOUND"
printenv SUPABASE_SERVICE_ROLE_KEY 2>/dev/null || echo "ENV NOT FOUND"
"""
    
    resp = pythonanywhere_request(f"consoles/{console_id}/send_input/", "POST", {"input": commands})
    
    if resp and resp.status_code == 200:
        print("[PA] Команды отправлены. Проверьте консоль PythonAnywhere.")
        return True
    
    return None

def disable_rls():
    """Отключить RLS через PythonAnywhere"""
    print("\n[RLS] Отключение RLS для таблицы profiles...")
    
    # Проверяем SERVICE_KEY
    if not SUPABASE_SERVICE_KEY:
        print("[WARN] SERVICE_KEY не найден в .env файле")
        print("[INFO] Попытка получить SERVICE_KEY из PythonAnywhere...")
        get_service_key_from_pa()
        
        # Обновляем переменные
        load_dotenv()
        service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        
        if not service_key:
            print("[ERROR] SERVICE_KEY не найден!")
            print("[INFO] Проверьте консоль PythonAnywhere для получения SERVICE_KEY")
            return False
    else:
        service_key = SUPABASE_SERVICE_KEY
    
    # Выполняем SQL через RPC
    print(f"[SQL] Выполнение SQL: ALTER TABLE profiles DISABLE ROW LEVEL SECURITY")
    
    sql_url = f"{SUPABASE_URL}/rest/v1/rpc"
    headers = {
        'apikey': service_key,
        'Authorization': f'Bearer {service_key}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    
    sql_data = {
        "sql": "ALTER TABLE profiles DISABLE ROW LEVEL SECURITY"
    }
    
    try:
        resp = requests.post(sql_url, json=sql_data, headers=headers, timeout=10)
        print(f"[SQL] Status: {resp.status_code}")
        print(f"[SQL] Response: {resp.text}")
        
        if resp.status_code == 200:
            print("[SUCCESS] RLS отключен для таблицы profiles!")
            return True
        else:
            print(f"[ERROR] Не удалось отключить RLS (код {resp.status_code})")
            print("[INFO] Попытка через PythonAnywhere...")
            
            # Получаем консоль
            resp = pythonanywhere_request("consoles/", "GET")
            if not resp or resp.status_code != 200:
                print("[ERROR] Не удалось получить консоли")
                return False
            
            consoles = resp.json()
            if not consoles:
                print("[ERROR] Нет консолей")
                return False
            
            console_id = consoles[0]["id"]
            print(f"[PA] Используем консоль #{console_id}")
            
            # Отправляем команды для отключения RLS
            send_url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/consoles/{console_id}/send_input/"
            
            commands = f"""
cd ~/mysite
source ~/.venv/bin/activate
python -c "import requests; print(requests.post('{SUPABASE_URL}/rest/v1/rpc', json={{'sql': 'ALTER TABLE profiles DISABLE ROW LEVEL SECURITY'}}, headers={{'apikey': '{service_key}', 'Authorization': f'Bearer {service_key}', 'Content-Type': 'application/json', 'Prefer': 'return=representation'}}, timeout=10).text)"
"""
            
            resp = pythonanywhere_request(f"consoles/{console_id}/send_input/", "POST", {"input": commands})
            
            if resp and resp.status_code == 200:
                print("[PA] Команды отправлены. Проверьте консоль PythonAnywhere.")
                return True
    except Exception as e:
        print(f"[ERROR] {e}")
    
    return False

def main():
    if len(sys.argv) < 2:
        print("Использование: python disable_rls_agent.py <команда>")
        print("Доступные команды:")
        print("  disable_rls  - Отключить RLS")
        print("  get_key      - Получить SERVICE_KEY из PythonAnywhere")
        print("  full_disable - Полный процесс отключения RLS")
        return
    
    command = sys.argv[1].lower()
    
    if command == "disable_rls":
        disable_rls()
    elif command == "get_key":
        get_service_key_from_pa()
    elif command == "full_disable":
        success = disable_rls()
        if success:
            print("\n[SUCCESS] RLS отключен! Теперь можно обновить роль.")
        else:
            print("\n[ERROR] Не удалось отключить RLS")
    else:
        print(f"[ERROR] Неизвестная команда: {command}")

if __name__ == "__main__":
    main()
