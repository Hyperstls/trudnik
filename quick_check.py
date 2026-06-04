#!/usr/bin/env python3
"""Быстрая проверка HTML на наличие max_workers"""

import requests

url = "https://hyperstls.pythonanywhere.com/job/new"

try:
    r = requests.get(url, timeout=30)
    print(f"Status: {r.status_code}")
    print(f"Length: {len(r.text)}")
    print(f"max_workers in HTML: {'max_workers' in r.text}")
    
    if 'max_workers' in r.text:
        # Найти строку с полем
        for i, line in enumerate(r.text.split('\n'), 1):
            if 'max_workers' in line:
                print(f"Line {i}: {line.strip()}")
except Exception as e:
    print(f"Error: {e}")
