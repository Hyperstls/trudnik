"""Заполнение seed-данных (религии, навыки) на проде через API админа."""
import os
import requests
from bs4 import BeautifulSoup
import re

BASE = "https://trudnik-hyperstls.amvera.io"
ADMIN_EMAIL = "admin@test.ru"
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')

session = requests.Session()

# 1. Логин
print("[1] Логин...")
r = session.post(f"{BASE}/login", data={
    "email": ADMIN_EMAIL,
    "password": ADMIN_PASSWORD
}, allow_redirects=False)
print(f"    Статус: {r.status_code}")
if r.status_code not in (302, 200):
    print(f"    Ошибка логина: {r.text[:200]}")
    exit(1)

# 2. Получить CSRF-токен с главной страницы
print("[2] Получение CSRF-токена...")
r = session.get(f"{BASE}/")
soup = BeautifulSoup(r.text, 'html.parser')
csrf_input = soup.find('input', {'name': '_csrf_token'})
if csrf_input:
    csrf_token = csrf_input.get('value', '')
    print(f"    Токен из input: {csrf_token[:30]}...")
else:
    # Пробуем найти в JavaScript
    match = re.search(r'[\'"]_csrf_token[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]', r.text)
    if match:
        csrf_token = match.group(1)
        print(f"    Токен из JS: {csrf_token[:30]}...")
    else:
        # Пробуем через cookie
        csrf_token = session.cookies.get('csrf_token', '')
        print(f"    Токен из cookie: {csrf_token[:30]}...")

# 3. Зайти в админку для получения актуального токена
print("[3] Заход в админку...")
r = session.get(f"{BASE}/admin")
soup = BeautifulSoup(r.text, 'html.parser')
csrf_input = soup.find('input', {'name': '_csrf_token'})
if csrf_input:
    csrf_token = csrf_input.get('value', '')
    print(f"    Токен: {csrf_token[:30]}...")

if not csrf_token:
    print("    CSRF-токен не найден!")
    exit(1)

headers = {
    "Content-Type": "application/json",
    "X-CSRFToken": csrf_token
}

# 4. Добавить религии
religions = [
    "Христианство", "Ислам", "Иудаизм",
    "Буддизм", "Индуизм", "Атеизм"
]

print("[4] Добавление религий...")
for name in religions:
    r = session.post(f"{BASE}/admin/religions",
                     json={"name": name},
                     headers=headers)
    status = "OK" if r.status_code == 200 else f"FAIL({r.status_code})"
    print(f"    {name}: {status}")

# 5. Добавить навыки
skills = [
    "Уборка", "Грузчик", "Курьер", "Строительство", "Ремонт",
    "Сантехника", "Электрика", "Покраска", "Садоводство", "Выгул собак",
    "Присмотр за детьми", "Репетиторство", "Переводы", "IT поддержка",
    "Дизайн", "Фото/видео", "Автомеханик", "Швея", "Повар", "Охрана"
]

print("[5] Добавление навыков...")
for name in skills:
    r = session.post(f"{BASE}/admin/skills",
                     json={"name": name},
                     headers=headers)
    status = "OK" if r.status_code == 200 else f"FAIL({r.status_code})"
    print(f"    {name}: {status}")

# 6. Проверка
print("\n[6] Проверка...")
r = session.get(f"{BASE}/api/religions")
data = r.json()
print(f"    Религии: {len(data.get('religions', []))} шт.")

r = session.get(f"{BASE}/api/skills")
data = r.json()
print(f"    Навыки: {len(data.get('skills', []))} шт.")

print("\nГотово!")
