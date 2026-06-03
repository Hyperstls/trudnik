import requests

SUPABASE_URL = "https://***REMOVED***.supabase.co"
SUPABASE_KEY = "***REMOVED***"

user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"

# Попытка обновить роль через анонимный ключ с указанием профиля
profile_update_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"

# Попробуем без заголовка Accept-Profile (по умолчанию будет текущий профиль)
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

# Обновим только роль через PATCH
update_data = {"role": "employer"}

print("=== Попытка обновить роль через анонимный ключ ===")
print(f"URL: {profile_update_url}")
print(f"Headers: {headers}")
print(f"Data: {update_data}")

resp = requests.patch(profile_update_url, json=update_data, headers=headers, timeout=10)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")

# Если не удалось, попробуем через POST (вставка новой записи с тем же ID - не сработает, это обновление)
# Попробуем использовать RPC функцию или напрямую обновить

# Попробуем через POST с upsert (обновление при конфликте)
print("\n=== Попытка через POST с upsert ===")
# Supabase не поддерживает upsert через обычный POST
# Попробуем через DELETE + POST (не рекомендуется)
# Или используем PATCH с правильными заголовками

# Попробуем найти правильный способ обновления
# Если RLS включен, то анонимный ключ не сможет обновить
# Нужно либо отключить RLS, либо использовать SERVICE_KEY

print("\n=== РЕШЕНИЕ: Создать политику RLS ===")
print("В Supabase dashboard:")
print("1. Перейти в Table Editor -> profiles")
print("2. Вкладка 'RLS' (Row Level Security)")
print("3. Создать политику UPDATE для анонимных пользователей:")
print("   - Target: UPDATE")
print("   - Role: authenticated")
print("   - USING (auth.uid() = id) OR role IS NULL")
print("   - WITH CHECK (auth.uid() = id)")
print("4. Или отключить RLS для profiles (не безопасно для продакшена)")
