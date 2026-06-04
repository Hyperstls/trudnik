#!/usr/bin/env python3
"""
Скрипт для проверки шаблона job_new.html
"""

# Локальный путь
local_path = "templates/job_new.html"

try:
    with open(local_path, 'r', encoding='utf-8') as f:
        local_content = f.read()
    
    print("ЛОКАЛЬНЫЙ ФАЙЛ:")
    print("-" * 60)
    print(f"Путь: {local_path}")
    print(f"Размер: {len(local_content)} символов")
    print(f"max_workers найден: {'ДА' if 'max_workers' in local_content else 'НЕТ'}")
    
    if 'max_workers' in local_content:
        for i, line in enumerate(local_content.split('\n'), 1):
            if 'max_workers' in line:
                print(f"Строка {i}: {line.strip()}")
    
    print("-" * 60)
    
    # Содержимое шаблона
    print("\nПОЛНОЕ СОДЕРЖИМОЕ ЛОКАЛЬНОГО ФАЙЛА:")
    print("=" * 60)
    print(local_content)
    
except Exception as e:
    print(f"Ошибка: {e}")
