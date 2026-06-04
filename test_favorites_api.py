#!/usr/bin/env python3
"""Проверка API избранного"""

import requests

session = requests.Session()

# Логинимся
session.post('https://hyperstls.pythonanywhere.com/login', data={
    'email': 'test_max_workers@example.com',
    'password': 'Test123456'
})

# Проверяем API
print("Проверка API /api/favorites/check")
r = session.post('https://hyperstls.pythonanywhere.com/api/favorites/check', 
                 json={'worker_id': 'some-id'})
print(f"Status: {r.status_code}")
print(f"Response: {r.text}")

print("\nПроверка API /api/favorites/add")
r = session.post('https://hyperstls.pythonanywhere.com/api/favorites/add', 
                 json={'worker_id': 'some-id'})
print(f"Status: {r.status_code}")
print(f"Response: {r.text}")
