"""
Обновление роли пользователя напрямую в базе данных через Supabase Python SDK
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()

# Попытка использовать supabase-py
try:
    from supabase import create_client, Client
    
    SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://***REMOVED***.supabase.co')
    SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    
    if not SERVICE_KEY:
        print("SERVICE_KEY не найден в .env")
        print("Пожалуйста, добавьте SERVICE_KEY в .env файл")
        print("Получить его можно в Supabase Dashboard -> Settings -> API -> service_role key")
        exit(1)
    
    print(f"SERVICE_KEY: {SERVICE_KEY[:20]}...")
    
    # Создаем клиент с сервисным ключом
    supabase: Client = create_client(SUPABASE_URL, SERVICE_KEY)
    
    user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"
    
    # Обновляем роль
    print(f"\n=== Обновление роли пользователя {user_id} на employer ===")
    
    result = supabase.table("profiles").update({"role": "employer", "full_name": "Тестовый Работодатель"}).eq("id", user_id).execute()
    
    print(f"Result: {result}")
    
    # Проверка
    print("\n=== Проверка профиля ===")
    profile = supabase.table("profiles").select("*").eq("id", user_id).execute()
    print(f"Profile: {profile}")
    
    if profile.data:
        user = profile.data[0]
        print(f"\nUser ID: {user.get('id')}")
        print(f"Role: {user.get('role')}")
        print(f"Full Name: {user.get('full_name')}")
        print(f"\nSUCCESS: Роль обновлена!")
    
except ImportError:
    print("supabase-py не установлен. Установите его командой:")
    print("  pip install supabase")
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
