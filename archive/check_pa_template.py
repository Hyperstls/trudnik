#!/usr/bin/env python3
"""
Скрипт для проверки шаблона на PythonAnywhere
"""

import os

# Путь к шаблону на PythonAnywhere
template_path = "/home/hyperstls/mysite/templates/job_new.html"

if os.path.exists(template_path):
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("[OK] Файл найден")
    print(f"Длина: {len(content)} символов")
    print(f"max_workers: {'ДА' if 'max_workers' in content else 'НЕТ'}")
    
    if 'max_workers' in content:
        for i, line in enumerate(content.split('\n'), 1):
            if 'max_workers' in line:
                print(f"Строка {i}: {line.strip()}")
else:
    print("[ERROR] Файл НЕ найден")
    print(f"Путь: {template_path}")
