#!/usr/bin/env python3
"""Простая проверка наличия max_workers в HTML через requests"""

import requests

# Страница создания задания
url = "https://hyperstls.pythonanywhere.com/job/new"

try:
    response = requests.get(url)
    print(f"[INFO] Status: {response.status_code}")
    
    if response.status_code == 200:
        html = response.text
        
        if "max_workers" in html:
            print("[OK] Поле max_workers НАЙДЕНО в HTML!")
            
            # Найти строку с полем
            for i, line in enumerate(html.split('\n'), 1):
                if "max_workers" in line.lower():
                    print(f"   Строка {i}: {line.strip()}")
        else:
            print("[ERROR] Поле max_workers НЕ найдено в HTML!")
            print(f"[INFO] Длина HTML: {len(html)} символов")
    else:
        print(f"[ERROR] Ошибка загрузки страницы: {response.status_code}")
        
except Exception as e:
    print(f"[ERROR] Исключение: {e}")
