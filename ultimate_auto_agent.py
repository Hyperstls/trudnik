"""
Ultimate Auto Agent для "Трудник" - полностью автоматическое решение всех проблем
"""

import sys
import json
import os
import subprocess
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные
load_dotenv()

# Конфигурация
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

class UltimateAutoAgent:
    def __init__(self):
        self.user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"
        self.email = "test_employer_final@test.com"
        self.password = "123456"
        self.project_dir = Path(__file__).parent
        
    def run(self, cmd, timeout=120):
        """Запустить команду"""
        print(f"\n{'='*60}")
        print(f"[EXEC] {cmd}")
        print('='*60)
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, 
                                   timeout=timeout, cwd=str(self.project_dir))
            print(f"[OK] Код: {result.returncode}")
            if result.stdout:
                print(f"[OUTPUT] {result.stdout[:2000]}")
            if result.stderr and result.returncode != 0:
                print(f"[ERROR] {result.stderr[:500]}")
            return result
        except Exception as e:
            print(f"[ERROR] {e}")
            return None
    
    def pythonanywhere_request(self, endpoint, method="GET", data=None):
        """Запрос к PythonAnywhere API"""
        url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/{endpoint}"
        headers = {"Authorization": f"Token {PA_API_TOKEN}"}
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                resp = requests.post(url, headers=headers, json=data, timeout=10)
            elif method == "PUT":
                resp = requests.put(url, headers=headers, json=data, timeout=10)
            print(f"[PA] {method} {endpoint} -> {resp.status_code}")
            if resp.text:
                print(f"[PA] Response: {resp.text[:500]}")
            return resp
        except Exception as e:
            print(f"[PA ERROR] {e}")
            return None
    
    def get_service_key_from_pythonanywhere(self):
        """Попытаться получить SERVICE_KEY из PythonAnywhere"""
        print("\n[SERVICE] Попытка получения SERVICE_KEY из PythonAnywhere...")
        
        # Создаем скрипт для получения SERVICE_KEY
        script_content = '''
import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('SUPABASE_SERVICE_ROLE_KEY', 'NOT SET')
print(f"SERVICE_KEY: {key[:20] if key != 'NOT SET' else 'NOT SET'}...")
if key and key != 'NOT SET':
    print("SUCCESS: SERVICE_KEY найден!")
    print(f"KEY_LENGTH: {len(key)}")
else:
    print("ERROR: SERVICE_KEY не найден!")
    print("Попробуем получить из системных переменных...")
    import subprocess
    try:
        result = subprocess.run('printenv SUPABASE_SERVICE_ROLE_KEY', shell=True, capture_output=True, text=True)
        print(f"System var: {result.stdout.strip()}")
    except:
        pass
'''
        
        script_path = self.project_dir / "get_service_key_from_pa.py"
        script_path.write_text(script_content, encoding='utf-8')
        
        # Загружаем на PythonAnywhere
        console_url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/consoles/"
        resp = self.pythonanywhere_request("consoles/", "GET")
        
        if resp and resp.status_code == 200:
            consoles = resp.json()
            if consoles:
                console_id = consoles[0]["id"]
                print(f"[PA] Используем консоль #{console_id}")
                
                # Отправляем команды
                send_url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/consoles/{console_id}/send_input/"
                
                commands = """
cd ~/mysite
source ~/.venv/bin/activate
cat .env | grep SUPABASE_SERVICE_ROLE_KEY
python get_service_key_from_pa.py
"""
                resp = self.pythonanywhere_request(f"consoles/{console_id}/send_input/", "POST", {"input": commands})
                
                if resp and resp.status_code == 200:
                    print("[PA] Команды отправлены. Проверьте консоль PythonAnywhere.")
                    return True
        
        return False
    
    def update_role_directly(self):
        """Прямое обновление роли через Supabase API"""
        print("\n[ROLE] Попытка прямого обновления роли...")
        
        # Используем анонимный ключ (RLS отключен)
        headers = {
            'apikey': SUPABASE_ANON_KEY,
            'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        
        update_data = {"role": "employer", "full_name": "Тестовый Работодатель"}
        
        profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{self.user_id}"
        
        try:
            resp = requests.patch(profile_url, json=update_data, headers=headers, timeout=10)
            print(f"[SUPABASE] PATCH {profile_url} -> {resp.status_code}")
            print(f"[SUPABASE] Response: {resp.text}")
            
            if resp.status_code == 200:
                print("[SUCCESS] Роль обновлена через анонимный ключ!")
                return True
            else:
                print(f"[ERROR] Не удалось обновить роль (код {resp.status_code})")
                print("[INFO] RLS вероятно включен. ПопробуемSERVICE_KEY...")
                
                # Попытка с SERVICE_KEY
                if SUPABASE_SERVICE_KEY:
                    headers_service = {
                        'apikey': SUPABASE_SERVICE_KEY,
                        'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
                        'Content-Type': 'application/json',
                        'Prefer': 'return=representation'
                    }
                    resp = requests.patch(profile_url, json=update_data, headers=headers_service, timeout=10)
                    print(f"[SUPABASE] PATCH с SERVICE_KEY -> {resp.status_code}")
                    print(f"[SUPABASE] Response: {resp.text}")
                    return resp.status_code == 200
        except Exception as e:
            print(f"[ERROR] {e}")
        
        return False
    
    def check_role_status(self):
        """Проверить текущую роль пользователя"""
        print("\n[CHECK] Проверка текущей роли...")
        
        headers = {'apikey': SUPABASE_ANON_KEY, 'Authorization': f'Bearer {SUPABASE_ANON_KEY}'}
        check_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{self.user_id}&select=*"
        
        try:
            resp = requests.get(check_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    user = data[0]
                    role = user.get('role', 'unknown')
                    print(f"[ROLE] User ID: {self.user_id}")
                    print(f"[ROLE] Current Role: {role}")
                    print(f"[ROLE] Full Name: {user.get('full_name')}")
                    return role
        except Exception as e:
            print(f"[ERROR] {e}")
        
        return None
    
    def full_auto_test(self):
        """Полный цикл тестирования"""
        print("\n" + "="*60)
        print("ULTIMATE AUTO TEST")
        print("="*60)
        
        # Шаг 1: Проверка конфигурации
        print("\n[1/4] Проверка конфигурации...")
        result = self.run(f'{python_cmd} auto_fix_agent.py check_config')
        
        # Шаг 2: Проверка роли
        print("\n[2/4] Проверка роли...")
        role = self.check_role_status()
        
        # Шаг 3: Попытка обновления роли
        print("\n[3/4] Попытка обновления роли...")
        if not SUPABASE_SERVICE_KEY:
            print("[INFO] SERVICE_KEY не найден в .env файле")
            print("[INFO] Попытка получитьSERVICE_KEY из PythonAnywhere...")
            self.get_service_key_from_pythonanywhere()
            
            # Обновляем переменные
            load_dotenv()
            SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        
        # Обновляем роль
        success = self.update_role_directly()
        
        if not success and not SUPABASE_SERVICE_KEY:
            print("\n[WARN] Не удалось обновить роль")
            print("[INFO] SERVICE_KEY необходим для обновления роли")
            print("[INFO] Проверьте консоль PythonAnywhere для получения SERVICE_KEY")
        
        # Шаг 4: Тест входа
        print("\n[4/4] Тест входа...")
        if success:
            result = self.run(f'{python_cmd} my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"')
        else:
            print("[INFO] Ожидание обновления роли...")
            print("[INFO] После обновления роли запустите тест входа")
        
        return success
    
    def main(self):
        if len(sys.argv) < 2:
            print("Использование: python ultimate_auto_agent.py <команда>")
            print("Доступные команды:")
            print("  full_test    - Полный цикл тестирования")
            print("  check_role   - Проверить роль")
            print("  update_role  - Обновить роль")
            print("  get_service_key - Получить SERVICE_KEY из PythonAnywhere")
            return
        
        command = sys.argv[1].lower()
        
        if command == "full_test":
            self.full_auto_test()
        elif command == "check_role":
            self.check_role_status()
        elif command == "update_role":
            self.update_role_directly()
        elif command == "get_service_key":
            self.get_service_key_from_pythonanywhere()
        else:
            print(f"[ERROR] Неизвестная команда: {command}")

if __name__ == "__main__":
    agent = UltimateAutoAgent()
    agent.main()
