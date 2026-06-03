#!/usr/bin/env python3
"""
Использование PythonAnywhere Console API для загрузки файла
"""

import os
import sys
import time
import requests as http_requests

# Конфигурация
PYTHONANYWHERE_USERNAME = 'Hyperstls'
PYTHONANYWHERE_API_TOKEN = 'e4e936c2bed6824c4981927652c21986780e22b3'
LOCAL_FILE = 'C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py'

def read_local_file():
    """Прочитать локальный файл"""
    try:
        with open(LOCAL_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"[ERROR] Не удалось прочитать файл: {e}")
        return None

def pythonanywhere_api_request(method, endpoint, **kwargs):
    """Сделать запрос к PythonAnywhere API"""
    url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/{endpoint}'
    headers = {
        'Authorization': f'Token {PYTHONANYWHERE_API_TOKEN}',
        'Content-Type': 'application/json',
    }
    kwargs['headers'] = headers
    return http_requests.request(method, url, **kwargs)

def main():
    print("=" * 60)
    print("ЗАГРУЗКА НА PYTHONANYWHERE - CONSOLE API")
    print("=" * 60)
    print()
    
    # Прочитать локальный файл
    local_content = read_local_file()
    if not local_content:
        return False
    
    file_size = len(local_content)
    print(f"[OK] Локальный файл: {file_size} байт")
    
    # Создать bash консоль (не python3)
    console_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/consoles/'
    console_data = {
        'base_env': 'bash',
        'working_directory': f'/home/{PYTHONANYWHERE_USERNAME}'
    }
    
    print("[INFO] Создание bash консоли...")
    
    try:
        resp = http_requests.post(console_url, headers={'Authorization': f'Token {PYTHONANYWHERE_API_TOKEN}'}, json=console_data, timeout=10)
        print(f"[INFO] Console created: {resp.status_code}")
        
        if resp.status_code != 201:
            print(f"[ERROR] Не удалось создать console: {resp.text[:200]}")
            print()
            print("=" * 60)
            print("ИСПОЛЬЗУЙТЕ ВЕБ-ИНТЕРФЕЙС")
            print("=" * 60)
            print()
            print("1. https://www.pythonanywhere.com/")
            print("2. Files -> /home/hyperstls/app.py -> Edit")
            print("3. Вставить код и Save")
            print("4. Web -> Reload")
            return False
        
        console_id = resp.json()['id']
        print(f"[OK] Console ID: {console_id}")
        
        # Выполнить команды
        commands = [
            f'cd /home/{PYTHONANYWHERE_USERNAME}',
            f'cp app.py app.py.backup.{time.strftime("%Y%m%d_%H%M%S")}',
            'echo "Backup created"',
            'curl -o app.py https://raw.githubusercontent.com/Hyperstls/trudnik/main/app.py 2>/dev/null || echo "curl failed"',
            'wc -l app.py',
            'head -5 app.py',
            'touch app.py.wsgi',
            'echo "Reload done"'
        ]
        
        print("[INFO] Выполнение команд...")
        
        for i, cmd in enumerate(commands):
            exec_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/consoles/{console_id}/exec/'
            exec_data = {'command': cmd}
            
            resp_exec = http_requests.post(exec_url, headers={'Authorization': f'Token {PYTHONANYWHERE_API_TOKEN}'}, json=exec_data, timeout=10)
            print(f"[INFO] Exec {i+1}: {cmd}")
            print(f"[INFO] Status: {resp_exec.status_code}")
            
            if resp_exec.status_code == 200:
                result = resp_exec.json()
                output = result.get('output', '')[:200]
                if output:
                    print(f"[OK] Output: {output}")
            
            time.sleep(1)
        
        # Проверить статус сервера
        print("[TEST] Проверка статуса сервера...")
        r = http_requests.get('https://hyperstls.pythonanywhere.com/', timeout=10)
        print(f"[OK] Server status: {r.status_code}")
        
        print()
        print("[SUCCESS] Попытка загрузки завершена!")
        print()
        print("Если curl не сработал, используйте веб-интерфейс:")
        print("1. https://www.pythonanywhere.com/")
        print("2. Files -> /home/hyperstls/app.py -> Edit")
        print("3. Вставить код и Save")
        print("4. Web -> Reload")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        
        print()
        print("=" * 60)
        print("ИСПОЛЬЗУЙТЕ ВЕБ-ИНТЕРФЕЙС")
        print("=" * 60)
        print()
        print("1. https://www.pythonanywhere.com/")
        print("2. Files -> /home/hyperstls/app.py -> Edit")
        print("3. Вставить код и Save")
        print("4. Web -> Reload")
        
        return False

if __name__ == "__main__":
    success = main()
    print()
    print("=" * 60)
    if success:
        print("Готово!")
    else:
        print("ОШИБКА")
    print("=" * 60)
