import sys
import io
import requests

BASE_URL = "https://hyperstls.pythonanywhere.com"

# Сессия requests для сохранения cookies
session = requests.Session()

# Вход
response = session.post(
    BASE_URL + "/login",
    data={"email": "new_employer4@test.com", "password": "Test123456"},
    allow_redirects=False
)

print(f"Login status: {response.status_code}")

# Получаем данные профиля
profile_url = BASE_URL + "/profile"
response = session.get(profile_url)

print(f"\nProfile status: {response.status_code}")

import re
# Ищем role в HTML (если она отображается)
role_match = re.search(r'role.*?(\w+)', response.text, re.IGNORECASE)
if role_match:
    print(f"Role in HTML: {role_match.group(1)}")

# Ищем flash сообщения
flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', response.text)
print(f"Flash messages: {flash_matches}")

# Ищем полное имя
name_match = re.search(r'<p[^>]*>([^<]*(?:Иван|Петров|Сидоров|Иванов)[^<]*)</p>', response.text)
if name_match:
    print(f"Name in profile: {name_match.group(1)}")

# Выведем часть HTML
print("\nHTML (first 1000 chars):", response.text[:1000])
