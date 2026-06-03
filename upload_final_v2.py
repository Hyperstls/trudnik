#!/usr/bin/env python3
"""
Загрузка app.py на PythonAnywhere через Console API
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

def main():
    print("=" * 60)
    print("ЗАГРУЗКА НА PYTHONANYWHERE - FINAL")
    print("=" * 60)
    print()
    
    # Прочитать локальный файл
    local_content = read_local_file()
    if not local_content:
        return False
    
    file_size = len(local_content)
    print(f"[OK] Локальный файл: {file_size} байт")
    
    # Создать консоль
    console_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/consoles/'
    console_data = {
        'base_env': 'python3',
        'working_directory': f'/home/{PYTHONANYWHERE_USERNAME}'
    }
    
    headers = {
        'Authorization': f'Token {PYTHONANYWHERE_API_TOKEN}',
        'Content-Type': 'application/json',
    }
    
    try:
        # Создать консоль
        resp = http_requests.post(console_url, headers=headers, json=console_data, timeout=10)
        print(f"[INFO] Console created: {resp.status_code}")
        
        if resp.status_code != 201:
            print(f"[ERROR] Не удалось создать console: {resp.text[:200]}")
            return False
        
        console_id = resp.json()['id']
        print(f"[OK] Console ID: {console_id}")
        
        # Выполнить команды для резервного копирования
        commands = [
            f'cd /home/{PYTHONANYWHERE_USERNAME}',
            f'cp app.py app.py.backup.{time.strftime("%Y%m%d_%H%M%S")}',
            'echo "Backup created"'
        ]
        
        for i, cmd in enumerate(commands):
            exec_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/consoles/{console_id}/exec/'
            exec_data = {'command': cmd}
            
            resp_exec = http_requests.post(exec_url, headers=headers, json=exec_data, timeout=10)
            print(f"[INFO] Exec {i+1}: {cmd}")
            
            if resp_exec.status_code == 200:
                result = resp_exec.json()
                print(f"[OK] Output: {result.get('output', '')[:200]}")
            
            time.sleep(0.5)
        
        # Создать Python скрипт для записи файла
        # Разбить на части из-за ограничения размера команды
        part_size = 1000
        parts = [local_content[i:i+part_size] for i in range(0, len(local_content), part_size)]
        
        print(f"[INFO] Файл разбит на {len(parts)} частей")
        
        # Выполнить Python код для записи файла
        python_script = f'''import sys
content_parts = {parts}
content = "".join(content_parts)
with open('/home/{PYTHONANYWHERE_USERNAME}/app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("File written successfully")
'''
        
        exec_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/consoles/{console_id}/exec/'
        exec_data = {'command': python_script[:4000]}  # Ограничение длины
        
        resp_exec = http_requests.post(exec_url, headers=headers, json=exec_data, timeout=30)
        print(f"[INFO] File upload status: {resp_exec.status_code}")
        
        if resp_exec.status_code == 200:
            result = resp_exec.json()
            print(f"[OK] Output: {result.get('output', '')[:500]}")
            
            # Перезапустить приложение
            print("[INFO] Перезапуск приложения...")
            webapp_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/webapps/hyperstls.pythonanywhere.com/'
            resp_reload = http_requests.post(webapp_url, headers=headers, timeout=10)
            print(f"[INFO] Reload status: {resp_reload.status_code}")
            
            if resp_reload.status_code == 200:
                print("[SUCCESS] Приложение перезапущено!")
                
                # Проверить статус
                print("[TEST] Проверка статуса сервера...")
                r = http_requests.get('https://hyperstls.pythonanywhere.com/', timeout=10)
                print(f"[OK] Server status: {r.status_code}")
                
                return True
        
        print("[FAIL] Не удалось загрузить файл")
        return False
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    print()
    print("=" * 60)
    if success:
        print("ЗАГРУЗКА ЗАВЕРШЕНА!")
    else:
        print("ОШИБКА - ПОПРОБУЙТЕ ВЕБ-ИНТЕРФЕЙС")
        print()
        print("1. https://www.pythonanywhere.com/")
        print("2. Files -> /home/hyperstls/app.py -> Edit")
        print("3. Вставить код и Save")
        print("4. Web -> Reload")
    print("=" * 60)
