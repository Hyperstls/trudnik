import sys
import io
import requests

BASE_URL = "https://hyperstls.pythonanywhere.com"

# Сессия requests для сохранения cookies
session = requests.Session()

# Вход как test_employer
response = session.post(
    BASE_URL + "/login",
    data={"email": "test_employer@test.com", "password": "Test123456"},
    allow_redirects=False
)

print(f"Login status: {response.status_code}")
print(f"Cookies: {session.cookies.get_dict()}")

# Проверяем my-jobs
my_jobs_url = BASE_URL + "/my-jobs"
response = session.get(my_jobs_url)

print(f"\nmy-jobs status: {response.status_code}")
print(f"Final URL: {response.url}")

import re
# Ищем flash сообщения
flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', response.text)
print(f"Flash messages: {flash_matches}")

# Ищем заголовок
h1_match = re.search(r'<h1[^>]*>([^<]*)</h1>', response.text)
if h1_match:
    print(f"H1: {h1_match.group(1)}")

# Выведем часть HTML
print("\nHTML (first 1000 chars):", response.text[:1000])
