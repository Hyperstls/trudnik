#!/usr/bin/env python3
"""
Ручная загрузка app.py на PythonAnywhere через веб-интерфейс
Метод: Открыть вкладку Files, нажать Edit, вставить код
"""

import os
import sys
import time
import requests as http_requests
from bs4 import BeautifulSoup

# Конфигурация
PYTHONANYWHERE_USERNAME = 'Hyperstls'
PYTHONANYWHERE_API_TOKEN = 'e4e936c2bed6824c4981927652c21986780e22b3'
LOCAL_FILE = 'C:/Users/s.prokopenko/PycharmProjects/trudnik/app.py'
LOGIN_URL = 'https://www.pythonanywhere.com/login/'
FILES_URL = f'https://www.pythonanywhere.com/user/{PYTHONANYWHERE_USERNAME}/files/home/{PYTHONANYWHERE_USERNAME}/app.py'

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
    print("РУЧНАЯ ЗАГРУЗКА НА PYTHONANYWHERE")
    print("=" * 60)
    print()
    
    local_content = read_local_file()
    if not local_content:
        return False
    
    file_size = len(local_content)
    print(f"[OK] Локальный файл: {file_size} байт")
    print()
    
    print("ИНСТРУКЦИЯ ДЛЯ ВЕБ-ИНТЕРФЕЙСА:")
    print("=" * 60)
    print()
    print("1. Открыть браузер")
    print("2. Перейти: https://www.pythonanywhere.com/login/")
    print("3. Войти как:", PYTHONANYWHERE_USERNAME)
    print()
    print("4. После входа перейти: https://www.pythonanywhere.com/user/")
    print("   Вкладка: Files")
    print()
    print("5. Найти файл: /home/hyperstls/app.py")
    print("6. Нажать: Edit (или значок карандаша)")
    print()
    print("7. В редакторе:")
    print("   - Выделить весь код (Ctrl+A)")
    print("   - Удалить (Delete)")
    print("   - Вставить обновлённый код (Ctrl+V)")
    print()
    print("8. Нажать: Save (внизу страницы)")
    print()
    print("9. Перейти во вкладку: Web")
    print("10. Нажать: Reload")
    print()
    print("=" * 60)
    print()
    
    # Проверка статуса сервера
    print("[TEST] Проверка статуса сервера...")
    try:
        r = http_requests.get('https://hyperstls.pythonanywhere.com/', timeout=10)
        print(f"[OK] Server status: {r.status_code}")
    except Exception as e:
        print(f"[ERROR] Ошибка проверки: {e}")
    
    print()
    print("Готово! После загрузки протестируйте:")
    print("1. Открыть: https://hyperstls.pythonanywhere.com/")
    print("2. Войти как: test_employer_final@test.com")
    print("3. Перейти в: /create-job")
    print("4. Заполнить форму и отправить")
    print("5. Ожидаем: 'Задание опубликовано' (не 500)")
    
    return True

if __name__ == "__main__":
    main()
