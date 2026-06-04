#!/usr/bin/env python3
"""Проверка содержимого страницы job_new с авторизацией"""

import requests

# Сессия для сохранения кук
session = requests.Session()

# 1. Перейти на страницу (будет перенаправление на login)
r1 = session.get('https://hyperstls.pythonanywhere.com/job/new')
print(f'Step 1: {r1.status_code} -> {r1.url}')

# 2. Зайти в систему
login_data = {
    'email': 'test_max_workers@example.com',
    'password': 'Test123456'
}
r2 = session.post('https://hyperstls.pythonanywhere.com/login', data=login_data)
print(f'Step 2: {r2.status_code} -> {r2.url}')

# 3. Перейти на страницу создания задания
r3 = session.get('https://hyperstls.pythonanywhere.com/job/new')
print(f'Step 3: {r3.status_code} -> {r3.url}')

# 4. Проверить наличие max_workers
if 'max_workers' in r3.text:
    print('\n[OK] max_workers найден на странице job/new')
else:
    print('\n[ERROR] max_workers НЕ найден на странице job/new')
    print('\nFirst 1000 chars of response:')
    print(r3.text[:1000])
