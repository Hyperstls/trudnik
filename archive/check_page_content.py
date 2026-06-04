#!/usr/bin/env python3
"""Проверка содержимого страницы job_new через curl"""

import subprocess

result = subprocess.run(
    ['curl', '-s', 'https://hyperstls.pythonanywhere.com/job/new'],
    capture_output=True,
    text=True
)

if 'max_workers' in result.stdout:
    print('[OK] max_workers найден на странице')
else:
    print('[ERROR] max_workers НЕ найден на странице')
    print('\nFirst 1000 chars of response:')
    print(result.stdout[:1000])
