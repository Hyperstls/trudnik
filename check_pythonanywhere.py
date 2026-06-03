import requests

PA_USERNAME = "Hyperstls"
PA_API_TOKEN = "e4e936c2bed6824c4981927652c21986780e22b3"

PA_HEADERS = {
    "Authorization": f"Token {PA_API_TOKEN}"
}

# Получаем список консолей
console_url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/consoles/"
resp = requests.get(console_url, headers=PA_HEADERS)

print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")

consoles = resp.json()
print(f"\nНайдено консолей: {len(consoles)}")
for c in consoles:
    print(f"  ID: {c.get('id')}, Type: {c.get('type')}, State: {c.get('state')}")

# Попробуем создать консоль
print("\n=== Попытка создания консоли ===")
create_url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/consoles/"
create_data = {
    "browser": "true",
    "console_path": "/"
}
resp_create = requests.post(create_url, headers=PA_HEADERS, json=create_data)
print(f"Status: {resp_create.status_code}")
print(f"Response: {resp_create.text}")
