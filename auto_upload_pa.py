#!/usr/bin/env python3
"""
Автоматическая загрузка app.py на PythonAnywhere
Метод: Web automation (Selenium/Playwright) - требует браузер
"""

import os
import sys
import time

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
    print("АВТОМАТИЧЕСКАЯ ЗАГРУЗКА НА PYTHONANYWHERE")
    print("=" * 60)
    print()
    
    local_content = read_local_file()
    if not local_content:
        return False
    
    file_size = len(local_content)
    print(f"[OK] Локальный файл: {file_size} байт")
    print()
    
    print("=" * 60)
    print("ИНСТРУКЦИЯ ДЛЯ АВТОМАТИЧЕСКОЙ ЗАГРУЗКИ")
    print("=" * 60)
    print()
    print("Способ 1: Использовать Selenium (если установлен)")
    print("  1. Установить: pip install selenium")
    print("  2. Установить WebDriver (ChromeDriver)")
    print("  3. Запустить скрипт с Selenium")
    print()
    
    print("Способ 2: Использовать Playwright (современный)")
    print("  1. Установить: pip install playwright")
    print("  2. Установить браузеры: playwright install")
    print("  3. Запустить скрипт с Playwright")
    print()
    
    print("Способ 3: Ручная загрузка (НАДЕЖНЫЙ)")
    print("  1. Открыть: https://www.pythonanywhere.com/login/")
    print("  2. Войти как: Hyperstls")
    print("  3. Files -> /home/hyperstls/app.py -> Edit")
    print("  4. Вставить код и Save")
    print("  5. Web -> Reload")
    print()
    
    # Проверка статуса сервера
    print("[TEST] Проверка статуса сервера...")
    try:
        import requests as http_requests
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
