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

print(f"Status: {response.status_code}")
print(f"Cookies after login: {session.cookies.get_dict()}")

# Проверяем заголовок Location (редирект)
print(f"Redirect location: {response.headers.get('Location', 'N/A')}")

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

# Проверяем my-jobs
my_jobs_url = BASE_URL + "/my-jobs"
response = session.get(my_jobs_url)

print(f"\nmy-jobs status: {response.status_code}")
print(f"Final URL: {response.url}")

flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', response.text)
print(f"Flash messages: {flash_matches}")

# Ищем role в ответе
if "Доступ только для работодателей" in response.text:
    print("ERROR: Доступ только для работодателей")
