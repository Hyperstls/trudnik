#!/usr/bin/env python3
"""
Загрузка app.py на PythonAnywhere через Web Console API
"""

import os
import sys
import time
import requests
from datetime import datetime

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
    return requests.request(method, url, **kwargs)

def main():
    print("=" * 60)
    print("ЗАГРУЗКА НА PYTHONANYWHERE")
    print("=" * 60)
    print()
    
    # Прочитать локальный файл
    local_content = read_local_file()
    if not local_content:
        return False
    
    file_size = len(local_content)
    print(f"[OK] Локальный файл: {file_size} байт")
    
    # Получить ID текущего файла для резервной копии
    print("[INFO] Получение информации о текущем файле...")
    file_path = f'files/path{PYTHONANYWHERE_USERNAME}/app.py'
    
    # Попытаться получить существующий файл
    try:
        resp = pythonanywhere_api_request('GET', f'files/path/home/{PYTHONANYWHERE_USERNAME}/app.py')
        print(f"[INFO] Статус запроса: {resp.status_code}")
        
        if resp.status_code == 200:
            print("[INFO] Файл найден, создание резервной копии...")
            # Сохранить резервную копию через bash
            bash_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/consoles/'
            
            # Создать console для выполнения команд
            console_data = {
                'base_env': 'python3',
                'working_directory': f'/home/{PYTHONANYWHERE_USERNAME}'
            }
            
            resp_console = pythonanywhere_api_request('POST', 'consoles/', json=console_data)
            print(f"[INFO] Console создана: {resp_console.status_code}")
            
            if resp_console.status_code == 201:
                console_id = resp_console.json()['id']
                print(f"[INFO] Console ID: {console_id}")
                
                # Выполнить команды
                commands = [
                    f'cd /home/{PYTHONANYWHERE_USERNAME}',
                    f'cp app.py app.py.backup.{datetime.now().strftime("%Y%m%d")}',
                    'echo "Резервная копия создана"'
                ]
                
                for cmd in commands:
                    exec_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/consoles/{console_id}/exec/'
                    exec_data = {'command': cmd}
                    
                    resp_exec = pythonanywhere_api_request('POST', f'consoles/{console_id}/exec/', json=exec_data)
                    print(f"[INFO] Выполнена: {cmd} -> {resp_exec.status_code}")
                    
                    if resp_exec.status_code == 200:
                        result = resp_exec.json()
                        print(f"[INFO] Результат: {result.get('output', '')[:100]}")
                    
                    time.sleep(0.5)
                
                # Загрузить новый файл
                print("[INFO] Загрузка нового файла...")
                
                # Использовать echo для создания файла
                echo_cmd = f'cat > app.py << \'ENDOFFILE\'\n{local_content[:500]}...[остальное пропущено для теста]ENDOFFILE'
                
                # Попытаться использовать curl для загрузки
                # Создать простой скрипт для загрузки
                curl_script = f'''
#!/bin/bash
cd /home/{PYTHONANYWHERE_USERNAME}
# Создать резервную копию
cp app.py app.py.backup.{datetime.now().strftime("%Y%m%d")}
echo "Резервная копия создана"

# Загрузить файл через wget (если доступен)
wget -O app.py https://raw.githubusercontent.com/Hyperstls/trudnik/main/app.py 2>/dev/null || \\
echo "wget не найден, используем другой метод"

# Если wget не работает, попробуем curl
curl -o app.py https://raw.githubusercontent.com/Hyperstls/trudnik/main/app.py 2>/dev/null || \\
echo "curl не найден"

# Проверить файл
wc -l app.py
head -5 app.py

# Перезапустить приложение
touch app.py.wsgi

echo "Готово!"
'''
                
                print("[INFO] Выполнение скрипта загрузки...")
                # Это будет сложно через API, используем простой curl на локальной машине
                
        else:
            print(f"[INFO] Нет существующего файла (статус: {resp.status_code})")
    except Exception as e:
        print(f"[WARN] Ошибка при получении файла: {e}")
    
    # Альтернативный метод: использование PythonAnywhere console через API
    print("[INFO] Попытка загрузки через console API...")
    
    try:
        # Создать новую консоль
        console_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/consoles/'
        console_data = {
            'base_env': 'python3',
            'working_directory': f'/home/{PYTHONANYWHERE_USERNAME}'
        }
        
        resp = pythonanywhere_api_request('POST', 'consoles/', json=console_data)
        print(f"[INFO] Console создана: {resp.status_code}")
        
        if resp.status_code == 201:
            console_id = resp.json()['id']
            print(f"[INFO] Console ID: {console_id}")
            
            # Выполнить команды для загрузки файла
            commands = [
                f'cd /home/{PYTHONANYWHERE_USERNAME}',
                f'cp app.py app.py.backup.{datetime.now().strftime("%Y%m%d")}',
                'echo "Резервная копия создана"'
            ]
            
            for cmd in commands:
                exec_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/consoles/{console_id}/exec/'
                exec_data = {'command': cmd}
                
                resp_exec = pythonanywhere_api_request('POST', f'consoles/{console_id}/exec/', json=exec_data)
                print(f"[INFO] {cmd} -> {resp_exec.status_code}")
                
                if resp_exec.status_code == 200:
                    result = resp_exec.json()
                    print(f"[INFO] {result.get('output', '')[:100]}")
                
                time.sleep(1)
            
            print("[SUCCESS] Резервная копия создана!")
            print()
            print("=" * 60)
            print("ДЛЯ ПОЛНОЙ ЗАГРУЗКИ ИСПОЛЬЗУЙТЕ ВЕБ-ИНТЕРФЕЙС")
            print("=" * 60)
            print()
            print("1. Открыть: https://www.pythonanywhere.com/")
            print("2. Files -> /home/hyperstls/app.py -> Edit")
            print("3. Вставить код и Save")
            print("4. Web -> Reload")
            
            return True
            
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
    
    return False

if __name__ == "__main__":
    main()
