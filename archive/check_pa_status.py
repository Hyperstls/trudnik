#!/usr/bin/env python
"""
Проверка и обновление файлов на PythonAnywhere через webftp
"""

import http.client
import urllib.parse
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Credentials (используем API token для авторизации)
API_TOKEN = os.getenv("PYTHONANYWHERE_API_TOKEN")
USERNAME = os.getenv("PYTHONANYWHERE_USERNAME", "Hyperstls")

if not API_TOKEN:
    raise RuntimeError(
        "PYTHONANYWHERE_API_TOKEN должен быть установлен в переменных окружения."
    )

# PythonAnywhere API
HOST = "www.pythonanywhere.com"
BASE_URL = f"/api/v0/user/{USERNAME}"

print("=== Проверка статуса PythonAnywhere ===\n")

# 1. Проверка статуса веб-приложения
print("1. Проверка статуса веб-приложения...")
try:
    conn = http.client.HTTPSConnection(HOST)
    headers = {
        "Authorization": f"Token {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    conn.request("GET", f"{BASE_URL}/webapps/hyperstls.pythonanywhere.com/", headers=headers)
    response = conn.getresponse()
    
    if response.status == 200:
        data = response.read().decode()
        print(f"   [OK] Статус: {response.status}")
        # Проверим, что приложение активно
        if '"active":true' in data or '"status":"active"' in data:
            print("   [OK] Приложение активно")
    else:
        print(f"   [ERR] Ошибка: {response.status}")
    
    conn.close()
except Exception as e:
    print(f"   [ERR] Исключение: {e}")

# 2. Перезагрузка веб-приложения
print("\n2. Перезагрузка веб-приложения...")
try:
    conn = http.client.HTTPSConnection(HOST)
    headers = {
        "Authorization": f"Token {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    conn.request("POST", f"{BASE_URL}/webapps/hyperstls.pythonanywhere.com/reload/", headers=headers)
    response = conn.getresponse()
    
    if response.status == 200:
        print(f"   [OK] Перезагрузка успешна! (код: {response.status})")
    else:
        print(f"   [ERR] Ошибка перезагрузки: {response.status}")
    
    conn.close()
except Exception as e:
    print(f"   [ERR] Исключение: {e}")

print("\n=== Готово! ===")
print("\nТеперь проверьте сайт:")
print("https://hyperstls.pythonanywhere.com")
print("\nВойдите как test_employer_final@test.com и попробуйте создать задание.")
