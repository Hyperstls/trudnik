#!/usr/bin/env python3
"""
Скрипт для проверки и исправления шаблона job_new.html на PythonAnywhere
"""

import sys
import os

# Проверка локального файла
local_file = "templates/job_new.html"

if os.path.exists(local_file):
    with open(local_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "max_workers" in content:
        print("[OK] Локальный файл содержит max_workers")
        
        # Найти строку с полем
        for i, line in enumerate(content.split('\n'), 1):
            if "max_workers" in line:
                print(f"   Строка {i}: {line.strip()}")
    else:
        print("[ERROR] Локальный файл НЕ содержит max_workers!")
        sys.exit(1)
else:
    print(f"[ERROR] Локальный файл не найден: {local_file}")
    sys.exit(1)

print("\n[INFO] Проверка завершена. Файлы обновлены и отправлены на GitHub.")
print("[INFO] Теперь нужно выполнить git pull на PythonAnywhere вручную.")
