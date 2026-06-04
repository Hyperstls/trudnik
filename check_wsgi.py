#!/usr/bin/env python3
"""Проверка WSGI файла"""

import os

# Возможные WSGI пути
WSGI_PATHS = [
    "/var/www/hyperstls_pythonanywhere_com_wsgi.py",
    "/var/www/trudnik_pythonanywhere_com_wsgi.py",
]

print("=" * 60)
print("ПРОВЕРКА WSGI ФАЙЛОВ")
print("=" * 60)

for path in WSGI_PATHS:
    print(f"\n[INFO] Проверка: {path}")
    if os.path.exists(path):
        print("  [FOUND]")
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"  Длина: {len(content)} символов")
        
        # Показать первые 500 символов
        print("\n  Первая строка:")
        for line in content.split('\n')[:3]:
            print(f"    {line}")
    else:
        print("  [NOT FOUND]")

print("\n" + "=" * 60)
