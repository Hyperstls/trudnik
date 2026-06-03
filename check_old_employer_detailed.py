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

print(f"Login POST status: {response.status_code}")
print(f"Cookies after POST: {session.cookies.get_dict()}")

# Если редирект,follow его
if response.status_code == 302:
    redirect_url = response.headers.get('Location')
    print(f"Redirect to: {redirect_url}")
    response = session.get(redirect_url)
    print(f"Redirect status: {response.status_code}")
    print(f"Cookies after redirect: {session.cookies.get_dict()}")

print(f"\nFinal URL: {response.url}")

# Ищем flash сообщения
import re
flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', response.text)
print(f"Flash messages: {flash_matches}")

# Ищем ошибки
error_matches = re.findall(r'Ошибка.*', response.text)
print(f"Error messages: {error_matches}")
