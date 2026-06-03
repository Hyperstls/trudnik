#!/usr/bin/env python3
"""Проверка сервера PythonAnywhere"""
import sys
sys.path.insert(0, '.venv/Lib/site-packages')
import requests

r = requests.get('https://hyperstls.pythonanywhere.com', timeout=10)
print('Server status:', r.status_code)
