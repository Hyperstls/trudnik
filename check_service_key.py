"""
Проверка SERVICE_KEY на PythonAnywhere
"""

import os
from dotenv import load_dotenv

load_dotenv()

SERVICE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')

print("=== Проверка SERVICE_KEY ===")
print(f"SERVICE_KEY: {SERVICE_KEY[:20] if SERVICE_KEY else 'NOT SET'}...")
print(f"SERVICE_KEY length: {len(SERVICE_KEY) if SERVICE_KEY else 0}")

if SERVICE_KEY:
    print("\nSERVICE_KEY найден!")
    print("Можно обновить роль через solution_rls.py")
else:
    print("\nSERVICE_KEY не найден!")
    print("Пожалуйста, добавьте его в .env файл на PythonAnywhere:")
    print("1. Перейдите в Supabase Dashboard -> Settings -> API")
    print("2. Скопируйте service_role key")
    print("3. Добавьте в .env файл на PythonAnywhere как SUPABASE_SERVICE_ROLE_KEY")
    print("4. Перезапустите приложение")
