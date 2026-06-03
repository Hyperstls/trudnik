#!/usr/bin/env python3
"""
Попытка загрузки файла через PythonAnywhere API
(не официальный API - может не работать)
"""

import requests
import os
import sys

# Конфигурация
LOCAL_FILE = 'C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py'
REMOTE_FILE = '/home/hyperstls/app.py'

# PythonAnywhere веб-интерфейс (надеемся, что API доступен)
PA_LOGIN_URL = 'https://www.pythonanywhere.com/account/login/'
PA_API_URL = 'https://www.pythonanywhere.com/api/v0/user/hyperstls/files/home/hyperstls/app.py'

def read_local_file():
    """Прочитать локальный файл"""
    try:
        with open(LOCAL_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"[ERROR] Не удалось прочитать файл: {e}")
        return None

def upload_via_requests():
    """Попытка загрузки через requests"""
    print("[INFO] Попытка загрузки через API PythonAnywhere...")
    
    local_content = read_local_file()
    if not local_content:
        return False
    
    # Создать сессию
    session = requests.Session()
    
    # Получить CSRF токен
    try:
        resp = session.get(PA_LOGIN_URL, timeout=10)
        csrf_token = session.cookies.get('csrftoken', '')
        print(f"[INFO] CSRF token: {csrf_token[:20] if csrf_token else 'NOT FOUND'}...")
    except Exception as e:
        print(f"[WARN] Не удалось получить CSRF token: {e}")
        csrf_token = ''
    
    # Попытаться загрузить
    print("[INFO] Отправка запроса...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Referer': 'https://www.pythonanywhere.com/',
    }
    
    if csrf_token:
        headers['X-CSRFToken'] = csrf_token
    
    # Попытаться загрузить через API
    try:
        response = session.put(
            PA_API_URL,
            headers=headers,
            json={'content': local_content},
            timeout=30
        )
        
        print(f"[INFO] Статус: {response.status_code}")
        print(f"[INFO] Ответ: {response.text[:200]}")
        
        if response.status_code in [200, 201]:
            print("[SUCCESS] Файл успешно загружен!")
            return True
        else:
            print(f"[FAIL] Ошибка загрузки: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Ошибка при загрузке: {e}")
        return False

def main():
    print("=" * 60)
    print("ПОПЫТКА ЗАГРУЗКИ НА PYTHONANYWHERE")
    print("=" * 60)
    print()
    
    # Проверить локальный файл
    if not os.path.exists(LOCAL_FILE):
        print(f"[ERROR] Локальный файл не найден: {LOCAL_FILE}")
        return False
    
    file_size = os.path.getsize(LOCAL_FILE)
    print(f"[OK] Локальный файл: {file_size} bytes")
    
    # Попытаться загрузить
    success = upload_via_requests()
    
    if not success:
        print()
        print("=" * 60)
        print("ИСПОЛЬЗУЙТЕ РУЧНОЙ СПОСОБ")
        print("=" * 60)
        print()
        print("1. Открыть: https://www.pythonanywhere.com/")
        print("2. Войти как: hyperstls")
        print("3. Вкладка: Files → /home/hyperstls/app.py → Edit")
        print("4. Вставить код и Save")
        print("5. Вкладка: Web → Reload")
    
    return success

if __name__ == "__main__":
    main()
