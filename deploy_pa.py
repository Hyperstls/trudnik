#!/usr/bin/env python
"""
Скрипт проверки и деплоя на PythonAnywhere
"""

import http.client
import json
import time

# Credentials
API_TOKEN = "e4e936c2bed6824c4981927652c21986780e22b3"
USERNAME = "Hyperstls"
HOST = "www.pythonanywhere.com"
BASE_URL = f"/api/v0/user/{USERNAME}"

def make_request(method, path, data=None):
    """Сделать запрос к PythonAnywhere API"""
    conn = http.client.HTTPSConnection(HOST)
    headers = {
        "Authorization": f"Token {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        if data:
            conn.request(method, path, json.dumps(data), headers)
        else:
            conn.request(method, path, headers=headers)
        
        response = conn.getresponse()
        result = response.read().decode()
        
        if response.status >= 400:
            print(f"   [ERR] {response.status}: {result}")
            return None
        
        return result
    except Exception as e:
        print(f"   [ERR] Исключение: {e}")
        return None
    finally:
        conn.close()

print("=== Деплой на PythonAnywhere ===\n")

# 1. Проверить статус веб-приложения
print("1. Проверка статуса веб-приложения...")
result = make_request("GET", f"{BASE_URL}/webapps/hyperstls.pythonanywhere.com/")
if result:
    print(f"   [OK] Приложение найдено")

# 2. Перезагрузить веб-приложение
print("\n2. Перезагрузка веб-приложения...")
result = make_request("POST", f"{BASE_URL}/webapps/hyperstls.pythonanywhere.com/reload/")
if result:
    print(f"   [OK] Перезагрузка инициирована: {result}")

# 3. Подождать
print("\n3. Ожидание завершения перезагрузки...")
time.sleep(5)

# 4. Проверить логи ошибок
print("\n4. Проверка логов ошибок...")
result = make_request("GET", f"{BASE_URL}/webapps/hyperstls.pythonanywhere.com/error_log/")
if result:
    # Проверим, есть ли ошибки за последнее время
    if "ERROR" in result or "Traceback" in result:
        print("   [WARN] Найдены ошибки в логах:")
        # Выведем последние 5 строк
        lines = result.split('\n')
        for line in lines[-5:]:
            if line.strip():
                print(f"      {line}")
    else:
        print("   [OK] Ошибок в логах не найдено")

print("\n=== Готово! ===")
print("\nТеперь проверьте сайт:")
print("https://hyperstls.pythonanywhere.com")
print("\nВойдите как test_employer_final@test.com и попробуйте создать задание.")
print("Если всё работает, ошибка 500 должна быть исправлена.")
