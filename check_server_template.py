#!/usr/bin/env python3
"""
Скрипт для проверки шаблона job_new.html на сервере PythonAnywhere
"""

import os
import sys

# Возможные пути к шаблону
POSSIBLE_PATHS = [
    "/var/www/hyperstls_pythonanywhere_com/templates/job_new.html",
    "/home/hyperstls/mysite/templates/job_new.html",
    "/var/www/trudnik_pythonanywhere_com/templates/job_new.html",
]

def check_templates():
    print("=" * 60)
    print("ПРОВЕРКА ШАБЛОНА job_new.html НА СЕРВЕРЕ")
    print("=" * 60)
    
    found = False
    
    for path in POSSIBLE_PATHS:
        print(f"\n[INFO] Проверка: {path}")
        
        if not os.path.exists(path):
            print("  [NOT FOUND]")
            continue
        
        print("  [FOUND]")
        found = True
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if "max_workers" in content:
            print("  [OK] max_workers НАЙДЕН!")
            
            # Найти строку с полем
            for i, line in enumerate(content.split('\n'), 1):
                if "max_workers" in line:
                    print(f"  Строка {i}: {line.strip()}")
        else:
            print("  [ERROR] max_workers НЕ найден!")
            print(f"  Длина файла: {len(content)} символов")
    
    print("\n" + "=" * 60)
    if found:
        print("Результат: Шаблон найден, проверьте наличие max_workers выше")
    else:
        print("Результат: Шаблон НЕ найден по ни одному из путей")
    print("=" * 60)

if __name__ == '__main__':
    check_templates()
