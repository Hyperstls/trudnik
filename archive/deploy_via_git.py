#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Деплой на PythonAnywhere через Git pull
"""

import http.client
import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Credentials
API_TOKEN = os.getenv("PYTHONANYWHERE_API_TOKEN")
USERNAME = os.getenv("PYTHONANYWHERE_USERNAME")

if not API_TOKEN or not USERNAME:
    raise RuntimeError(
        "PYTHONANYWHERE_API_TOKEN и PYTHONANYWHERE_USERNAME должны быть "
        "установлены в переменных окружения."
    )

HOST = "www.pythonanywhere.com"

print("=== Деплой через Git на PythonAnywhere ===\n")

# Создать console
print("1. Создание console...")
try:
    conn = http.client.HTTPSConnection(HOST)
    headers = {
        "Authorization": f"Token {API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = json.dumps({"command": "cd ~/mysite && git pull && touch app.py.wsgi"})
    conn.request("POST", f"/api/v0/user/{USERNAME}/consoles/", data, headers)
    response = conn.getresponse()
    
    result = response.read().decode()
    print(f"   Status: {response.status}")
    print(f"   Response: {result[:200]}...")
    
    conn.close()
except Exception as e:
    print(f"   [ERR] Ошибка: {e}")

print("\n=== Готово! ===")
print("Git pull должен быть выполнен на PythonAnywhere.")
print("Изменения загружены через git.")
