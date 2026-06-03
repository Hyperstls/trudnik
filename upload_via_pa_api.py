#!/usr/bin/env python3
"""
Загрузка app.py на PythonAnywhere через API
Использует официальный API PythonAnywhere
"""

import os
import sys
import requests
import json

# Конфигурация
LOCAL_FILE = 'C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py'
PYTHONANYWHERE_API_TOKEN = os.getenv('PYTHONANYWHERE_API_TOKEN', 'e4e936c2bed6824c4981927652c21986780e22b3')
PYTHONANYWHERE_USERNAME = 'Hyperstls'
REMOTE_PATH = '/home/hyperstls/app.py'

def read_local_file():
    """Прочитать локальный файл"""
    try:
        with open(LOCAL_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"[ERROR] Не удалось прочитать файл: {e}")
        return None

def upload_to_pythonanywhere():
    """Загрузить файл на PythonAnywhere через API"""
    print("=" * 60)
    print("ЗАГРУЗКА НА PYTHONANYWHERE ЧЕРЕЗ API")
    print("=" * 60)
    print()
    
    # Прочитать локальный файл
    local_content = read_local_file()
    if not local_content:
        return False
    
    file_size = len(local_content)
    print(f"[OK] Локальный файл: {file_size} байт")
    
    # Создать резервную копию
    print("[INFO] Создание резервной копии...")
    copy_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/files/path{REMOTE_PATH}'
    backup_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/files/path{REMOTE_PATH}.backup.20260603'
    
    headers = {
        'Authorization': f'Token {PYTHONANYWHERE_API_TOKEN}',
        'Content-Type': 'application/json',
    }
    
    # Сначала скопировать существующий файл в резервную копию
    try:
        # Получить существующий файл (GET запрос)
        resp = requests.get(copy_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            existing_content = resp.json().get('content', '')
            if existing_content:
                # Сохранить резервную копию
                backup_payload = {
                    'content': existing_content,
                    'format': 'text'
                }
                resp_backup = requests.put(backup_url, headers=headers, json=backup_payload, timeout=10)
                if resp_backup.status_code in [200, 201]:
                    print("[OK] Резервная копия создана")
                else:
                    print(f"[WARN] Не удалось создать резервную копию: {resp_backup.status_code}")
            else:
                print("[INFO] Нет существующего файла для резервного копирования")
        else:
            print(f"[INFO] Нет существующего файла (статус: {resp.status_code})")
    except Exception as e:
        print(f"[WARN] Ошибка при создании резервной копии: {e}")
    
    # Загрузить обновлённый файл
    print("[INFO] Загрузка обновлённого файла...")
    
    payload = {
        'content': local_content,
        'format': 'text'
    }
    
    try:
        resp = requests.put(copy_url, headers=headers, json=payload, timeout=30)
        
        print(f"[INFO] Статус: {resp.status_code}")
        print(f"[INFO] Ответ: {resp.text[:300]}")
        
        if resp.status_code in [200, 201]:
            print("[SUCCESS] Файл успешно загружен!")
            
            # Перезапустить приложение
            print("[INFO] Перезапуск приложения...")
            webapp_url = f'https://www.pythonanywhere.com/api/v0/user/{PYTHONANYWHERE_USERNAME}/webapps/hyperstls.pythonanywhere.com/'
            
            resp_reload = requests.post(webapp_url, headers=headers, timeout=10)
            
            if resp_reload.status_code == 200:
                print("[OK] Приложение перезапущено!")
            else:
                print(f"[WARN] Перезапуск приложения: {resp_reload.status_code}")
                print(f"[INFO] {resp_reload.text[:200]}")
            
            return True
        else:
            print(f"[FAIL] Ошибка загрузки: {resp.status_code}")
            print(f"[INFO] {resp.text[:500]}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Ошибка при загрузке: {e}")
        return False

def test_after_upload():
    """Проверить работу после загрузки"""
    print()
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ПОСЛЕ ЗАГРУЗКИ")
    print("=" * 60)
    print()
    
    # Проверить статус сервера
    print("[TEST] Проверка статуса сервера...")
    try:
        resp = requests.get('https://hyperstls.pythonanywhere.com/', timeout=10)
        if resp.status_code == 200:
            print("[OK] Сервер доступен")
        else:
            print(f"[FAIL] Статус: {resp.status_code}")
    except Exception as e:
        print(f"[FAIL] Ошибка: {e}")
    
    print()
    print("Теперь протестируйте создание задания вручную:")
    print("1. Открыть: https://hyperstls.pythonanywhere.com/")
    print("2. Войти как: test_employer_final@test.com")
    print("3. Перейти в: /create-job")
    print("4. Заполнить форму и отправить")
    print("5. Ожидаем: 'Задание опубликовано' (не 500)")

def main():
    """Главная функция"""
    # Проверить переменные окружения
    if not PYTHONANYWHERE_API_TOKEN:
        print("[ERROR] PYTHONANYWHERE_API_TOKEN не найден")
        return False
    
    if not PYTHONANYWHERE_USERNAME:
        print("[ERROR] PYTHONANYWHERE_USERNAME не найден")
        return False
    
    # Выполнить загрузку
    success = upload_to_pythonanywhere()
    
    if success:
        test_after_upload()
        print()
        print("=" * 60)
        print("ОБНОВЛЕНИЕ ЗАВЕРШЕНО!")
        print("=" * 60)
    else:
        print()
        print("=" * 60)
        print("ОШИБКА ЗАГРУЗКИ")
        print("=" * 60)
        print()
        print("Попробуйте ручную загрузку:")
        print("1. https://www.pythonanywhere.com/")
        print("2. Files → /home/hyperstls/app.py → Edit")
        print("3. Вставить код и Save")
        print("4. Web → Reload")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
