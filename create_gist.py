#!/usr/bin/env python3
"""
Создать Gist на GitHub для загрузки файла на PythonAnywhere
"""

import os
import sys
import requests
import json

# GitHub токен (должен иметь права gists)
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '')

# Читаем локальный файл
LOCAL_FILE = 'C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py'
try:
    with open(LOCAL_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
except Exception as e:
    print(f"[ERROR] Не удалось прочитать файл: {e}")
    sys.exit(1)

print(f"[OK] Локальный файл: {len(content)} байт")

# Создаём Gist
url = "https://api.github.com/gists"
headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

data = {
    "description": "Trudnik app.py - обновлённый файл 2026-06-03",
    "public": False,
    "files": {
        "app.py": {
            "content": content
        }
    }
}

try:
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    
    gist = response.json()
    print(f"[SUCCESS] Gist создан!")
    print(f"[INFO] URL: {gist['html_url']}")
    print(f"[INFO] raw URL: {gist['files']['app.py']['raw_url']}")
    
    # Сохранить raw URL для использования на PythonAnywhere
    with open('GIST_URL.txt', 'w') as f:
        f.write(gist['files']['app.py']['raw_url'])
    
    print(f"[OK] Raw URL сохранён в GIST_URL.txt")
    
except Exception as e:
    print(f"[ERROR] Ошибка при создании Gist: {e}")
    print()
    print("Попробуйте:")
    print("1. Создать Gist вручную на https://gist.github.com/")
    print("2. Скопировать raw URL")
    print("3. Выполнить на PythonAnywhere: curl -o app.py <raw_url>")
