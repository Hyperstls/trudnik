import sys
import io
import requests

BASE_URL = "https://hyperstls.pythonanywhere.com"

# Сессия requests для сохранения cookies
session = requests.Session()

# Вход
response = session.post(
    BASE_URL + "/login",
    data={"email": "test_admin@test.com", "password": "Test123456"},
    allow_redirects=False
)

print(f"Login status: {response.status_code}")
print(f"Cookies after login: {session.cookies.get_dict()}")

# Проверяем my-jobs
my_jobs_url = BASE_URL + "/my-jobs"
response = session.get(my_jobs_url)

print(f"\nmy-jobs status: {response.status_code}")
print(f"Final URL: {response.url}")

import re
# Ищем flash сообщения
flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', response.text)
print(f"Flash messages: {flash_matches}")

# Ищем "Доступ только для работодателей"
if "Доступ только для работодателей" in response.text:
    print("ERROR: Доступ только для работодателей")
