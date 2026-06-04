#!/usr/bin/env python3
"""Проверка, что приложение перезагрузилось и содержит max_workers"""

import requests

r = requests.get('https://hyperstls.pythonanywhere.com/job/new')

print('Status:', r.status_code)
print('Has max_workers:', 'max_workers' in r.text)

if r.status_code == 200 and 'max_workers' in r.text:
    print('\n[OK] Приложение перезагрузилось и содержит max_workers')
else:
    print('\n[ERROR] Приложение НЕ перезагрузилось или содержит ошибки')
    print('\nFirst 500 chars of response:')
    print(r.text[:500])
