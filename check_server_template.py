#!/usr/bin/env python3
"""
Скрипт для проверки шаблона job_new.html на сервере PythonAnywhere
Запустить через: python check_server_template.py
"""

import os
import sys

# Путь к шаблону на PythonAnywhere
TEMPLATE_PATH = "/var/www/trudnik_pythonanywhere_com/templates/job_new.html"

def check_template():
    print("=" * 60)
    print("ПРОВЕРКА ШАБЛОНА job_new.html НА СЕРВЕРЕ")
    print("=" * 60)
    
    if not os.path.exists(TEMPLATE_PATH):
        print(f"\n[ERROR] Файл НЕ найден по пути: {TEMPLATE_PATH}")
        print("[INFO] Это означает, что git pull не был выполнен или путь неправильный")
        print("\n[INFO] Возможные пути:")
        print("  /var/www/hyperstls_pythonanywhere_com/templates/job_new.html")
        print("  /home/hyperstls/mysite/templates/job_new.html")
        return False
    
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "max_workers" in content:
        print("\n[OK] Поле max_workers НАЙДЕНО в шаблоне!")
        
        # Показать строку с полем
        for i, line in enumerate(content.split('\n'), 1):
            if "max_workers" in line:
                print(f"  Строка {i}: {line.strip()}")
        
        # Проверить, что это правильный HTML
        if '<input type="number" name="max_workers"' in content:
            print("\n[OK] Найдено правильное поле input с name='max_workers'")
            return True
        else:
            print("\n[WARN] Поле есть, но может быть скрыто или неправильно настроено")
            return False
    else:
        print("\n[ERROR] Поле max_workers НЕ найдено в шаблоне!")
        print(f"[INFO] Длина файла: {len(content)} символов")
        
        # Показать последние строки файла
        lines = content.split('\n')
        print("\n[INFO] Последние 10 строк файла:")
        for line in lines[-10:]:
            print(f"  {line}")
        
        return False

if __name__ == '__main__':
    success = check_template()
    
    print("\n" + "=" * 60)
    if success:
        print("Результат: Шаблон содержит поле max_workers")
    else:
        print("Результат: Шаблон НЕ содержит поле max_workers")
        print("\n[INFO] ПЕЧАТАЕМ ПОЛНЫЙ СОДЕРЖИМЫЕ ФАЙЛА ДЛЯ ОТЛАДКИ:")
        print("-" * 60)
        if os.path.exists(TEMPLATE_PATH):
            with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
                print(f.read())
    print("=" * 60)
