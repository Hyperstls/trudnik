#!/usr/bin/env python
"""
Проверка и обновление файлов на PythonAnywhere через webftp
"""

import http.client
import urllib.parse

# Credentials (используем API token для авторизации)
API_TOKEN = "e4e936c2bed6824c4981927652c21986780e22b3"

# PythonAnywhere API
HOST = "www.pythonanywhere.com"
BASE_URL = f"/api/v0/user/Hyperstls"

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
