"""Создать/восстановить тестовые аккаунты для Selenium-тестов."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

TEST_USERS = [
    {"email": "admin@test.ru", "password": "Step@1986", "role": "admin", "name": "Admin Test"},
    {"email": "org@test.ru", "password": "Step@1986", "role": "employer", "name": "Org Test"},
    {"email": "trud@test.ru", "password": "Step@1986", "role": "worker", "name": "Trud Test"},
]

headers = {
    "Authorization": f"Bearer {SERVICE_KEY}",
    "apikey": ANON_KEY,
    "Content-Type": "application/json",
}

# Сначала получим ВСЕХ пользователей (без фильтра) и найдём нужных
print("Получаю список всех пользователей...")
list_url = f"{SUPABASE_URL}/auth/v1/admin/users"
all_resp = requests.get(list_url, headers=headers, timeout=10)
all_users = all_resp.json().get("users", []) if all_resp.ok else []
print(f"  -> найдено пользователей: {len(all_users)}")

# Строим словарь email -> user
users_by_email = {u["email"]: u for u in all_users if u.get("email")}

for user in TEST_USERS:
    existing = users_by_email.get(user["email"])
    
    if existing:
        user_id = existing["id"]
        print(f"[EXISTS] {user['email']} (id={user_id[:12]}...) — обновляю пароль и профиль")
        # Обновить пароль
        update_url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"
        update_resp = requests.put(update_url, headers=headers, json={
            "password": user["password"],
            "email_confirm": True,
        }, timeout=10)
        if update_resp.ok:
            print(f"  -> пароль обновлён")
        else:
            print(f"  -> ошибка обновления: {update_resp.status_code} {update_resp.text[:200]}")
    else:
        print(f"[CREATE] {user['email']} — регистрирую")
        create_url = f"{SUPABASE_URL}/auth/v1/admin/users"
        create_resp = requests.post(create_url, headers=headers, json={
            "email": user["email"],
            "password": user["password"],
            "email_confirm": True,
            "user_metadata": {"name": user["name"]},
        }, timeout=10)
        if create_resp.ok:
            data = create_resp.json()
            user_id = data["id"]
            print(f"  -> создан: {user_id[:12]}...")
        else:
            print(f"  -> ошибка создания: {create_resp.status_code} {create_resp.text[:200]}")
            continue
    
    # Обновить профиль (роль, имя)
    profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
    profile_headers = {
        "Authorization": f"Bearer {SERVICE_KEY}",
        "apikey": ANON_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    
    # Проверить, есть ли профиль
    check = requests.get(profile_url + "&select=id", headers=profile_headers, timeout=10)
    profile_data = {
        "role": user["role"],
        "full_name": user["name"],
    }
    
    if check.ok and check.json():
        # PATCH существующий
        patch = requests.patch(profile_url, headers=profile_headers, json=profile_data, timeout=10)
        print(f"  -> профиль обновлён: {patch.status_code}")
    else:
        # INSERT
        profile_data["id"] = user_id
        insert_url = f"{SUPABASE_URL}/rest/v1/profiles"
        post = requests.post(insert_url, headers=profile_headers, json=profile_data, timeout=10)
        print(f"  -> профиль создан: {post.status_code}")

# 3. Проверить логин
print("\nПроверка логина:")
auth_headers = {"apikey": ANON_KEY, "Content-Type": "application/json"}
for user in TEST_USERS:
    login_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    resp = requests.post(login_url, json={
        "email": user["email"],
        "password": user["password"],
    }, headers=auth_headers, timeout=10)
    if resp.ok:
        print(f"  [OK] {user['email']} — логин успешен")
    else:
        print(f"  [FAIL] {user['email']} — {resp.status_code}: {resp.json().get('error_description', resp.text[:100])}")

print("\nГотово!")
